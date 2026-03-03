import os
import re
import uuid
import time
import subprocess
import sys
from flask import Flask, render_template, request, jsonify, Response, abort
import yt_dlp
import imageio_ffmpeg

# ✅ تحديث yt-dlp تلقائياً عند كل بدء تشغيل — يحل مشكلة YouTube
try:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "-q"],
        check=True, timeout=120
    )
    print("[INFO] yt-dlp updated successfully.")
except Exception as e:
    print(f"[WARN] Could not update yt-dlp: {e}")

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# ✅ User-Agent حديث — يحل مشكلة TikTok 403
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ✅ BASE_OPTS — نظيف تماماً بدون format
BASE_OPTS = {
    "quiet":               True,
    "no_warnings":         True,
    "nocheckcertificate":  True,
    "extract_flat":        False,
    "http_headers": {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    },
}

if os.path.exists("cookies.txt"):
    BASE_OPTS["cookiefile"] = "cookies.txt"


def is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def is_tiktok(url: str) -> bool:
    return "tiktok.com" in url or "vm.tiktok.com" in url


def get_extract_opts(url: str) -> dict:
    """إعدادات الاستخراج حسب المنصة."""
    opts = dict(BASE_OPTS)

    if is_tiktok(url):
        # TikTok يحتاج Referer خاص لتجنب 403
        opts["http_headers"] = {
            **opts["http_headers"],
            "Referer": "https://www.tiktok.com/",
        }

    return opts


def get_stream_opts(url: str, filepath: str) -> dict:
    """إعدادات التحميل للبث حسب المنصة."""
    opts = get_extract_opts(url)

    if is_youtube(url):
        # YouTube: فيديو + صوت منفصلان يُدمجان بـ ffmpeg
        fmt = (
            "bestvideo[height<=480]+bestaudio"
            "/best[height<=480]"
            "/best"
        )
    elif is_tiktok(url):
        # TikTok: عادةً mp4 مدمج مسبقاً
        fmt = "best[ext=mp4]/best"
    else:
        # باقي المنصات
        fmt = (
            "bestvideo[height<=480]+bestaudio"
            "/best[height<=480]"
            "/best"
        )

    opts.update({
        "ffmpeg_location":     FFMPEG_PATH,
        "format":              fmt,
        "outtmpl":             filepath,
        "merge_output_format": "mp4",
        "retries":             5,
        "fragment_retries":    5,
        "ignoreerrors":        False,
    })

    return opts


def get_best_direct_url(info: dict):
    """أفضل رابط تحميل مباشر (video+audio مدمجان)."""
    formats = info.get("formats", [])

    # الأولوية 1: mp4 مدمج بأعلى دقة
    best = None
    best_height = 0
    for f in formats:
        if (f.get('vcodec') not in ('none', None)
                and f.get('acodec') not in ('none', None)
                and f.get('ext') == 'mp4'
                and f.get('url')):
            h = f.get('height') or 0
            if h > best_height:
                best_height = h
                best = f['url']
    if best:
        return best

    # الأولوية 2: أي صيغة مدمجة
    for f in reversed(formats):
        if (f.get('vcodec') not in ('none', None)
                and f.get('acodec') not in ('none', None)
                and f.get('url')):
            return f['url']

    return info.get('url')


def cleanup_old_files():
    try:
        now = time.time()
        for fname in os.listdir(DOWNLOAD_FOLDER):
            fpath = os.path.join(DOWNLOAD_FOLDER, fname)
            if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 7200:
                os.remove(fpath)
    except Exception:
        pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/download", methods=["POST"])
def download():
    cleanup_old_files()

    body = request.get_json()
    if not body or not body.get("url"):
        return jsonify({"error": "رابط غير صالح."}), 400

    url      = body["url"].strip()
    file_id  = str(uuid.uuid4())
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    title     = "Video"
    thumbnail = "https://img.icons8.com/color/96/000000/video.png"
    dl_url    = None
    fb_url    = None

    # ══ PHASE 1: استخراج المعلومات فقط — بدون تحميل ══
    try:
        extract_opts = get_extract_opts(url)
        with yt_dlp.YoutubeDL(extract_opts) as ydl:
            info      = ydl.extract_info(url, download=False)
            title     = info.get("title", title)
            thumbnail = info.get("thumbnail", thumbnail)
            fb_url    = info.get("url")
            dl_url    = get_best_direct_url(info)
    except yt_dlp.utils.DownloadError as e:
        err_msg = str(e)
        # رسائل خطأ واضحة للمستخدم
        if "403" in err_msg:
            return jsonify({"error": "المنصة رفضت الطلب (403). قد تحتاج ملف cookies.txt"}), 500
        if "Private video" in err_msg:
            return jsonify({"error": "هذا الفيديو خاص ولا يمكن الوصول إليه."}), 500
        if "This video is unavailable" in err_msg:
            return jsonify({"error": "الفيديو غير متاح أو محذوف."}), 500
        return jsonify({"error": f"فشل استخراج المعلومات: {err_msg}"}), 500
    except Exception as e:
        return jsonify({"error": f"خطأ غير متوقع: {str(e)}"}), 500

    # ══ PHASE 2: تحميل الفيديو على السيرفر للبث ══
    stream_url   = ""
    preview_type = "video"

    try:
        stream_opts = get_stream_opts(url, filepath)

        with yt_dlp.YoutubeDL(stream_opts) as ydl:
            ydl.download([url])

        # البحث عن الملف المُحمَّل
        final = None
        for fname in os.listdir(DOWNLOAD_FOLDER):
            if fname.startswith(file_id):
                if fname.endswith(".mp4"):
                    final = fname
                    break
                final = fname  # fallback لأي امتداد

        if final:
            stream_url = f"/stream/{final}"
        else:
            raise FileNotFoundError("الملف لم يُوجد بعد التحميل.")

    except Exception as e:
        preview_type = "error"
        print(f"[STREAM ERROR] {e}")

    return jsonify({
        "title":             title,
        "thumbnail":         thumbnail,
        "stream_url":        stream_url,
        "preview_type":      preview_type,
        "download_url_high": dl_url,
        "download_url_low":  fb_url,
    })


# ══ STREAM — دعم كامل لـ Range Requests ══
@app.route("/stream/<filename>")
def stream_video(filename):
    filename = os.path.basename(filename)  # حماية Path Traversal
    path     = os.path.join(DOWNLOAD_FOLDER, filename)

    if not os.path.exists(path):
        abort(404)

    size = os.path.getsize(path)
    rng  = request.headers.get("Range")

    if not rng:
        return Response(
            _read_chunks(path),
            status=200,
            mimetype="video/mp4",
            headers={
                "Content-Length": str(size),
                "Accept-Ranges":  "bytes",
                "Cache-Control":  "no-cache",
            }
        )

    m = re.search(r"bytes=(\d+)-(\d*)", rng)
    if not m:
        abort(416)

    b1 = int(m.group(1))
    b2 = int(m.group(2)) if m.group(2) else size - 1
    b2 = min(b2, size - 1)
    if b1 > b2:
        abort(416)

    ln = b2 - b1 + 1
    return Response(
        _read_chunks(path, b1, ln),
        status=206,
        mimetype="video/mp4",
        headers={
            "Content-Range":  f"bytes {b1}-{b2}/{size}",
            "Accept-Ranges":  "bytes",
            "Content-Length": str(ln),
            "Cache-Control":  "no-cache",
        }
    )


def _read_chunks(path, start=0, length=None):
    CHUNK = 1024 * 1024  # 1MB
    with open(path, "rb") as f:
        f.seek(start)
        remaining = length
        while True:
            sz   = CHUNK if remaining is None else min(CHUNK, remaining)
            data = f.read(sz)
            if not data:
                break
            if remaining is not None:
                remaining -= len(data)
            yield data


if __name__ == "__main__":
    app.run(debug=True, port=5000)
