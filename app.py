import os
import re
import uuid
import time
import subprocess
import sys
import urllib.parse
from flask import Flask, render_template, request, jsonify, Response, abort
import yt_dlp
import imageio_ffmpeg

# ✅ تحديث yt-dlp عند كل تشغيل
try:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "-q"],
        check=True, timeout=120
    )
    print("[INFO] yt-dlp updated.")
except Exception as e:
    print(f"[WARN] {e}")

app = Flask(__name__)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BASE_OPTS = {
    "quiet":              True,
    "no_warnings":        True,
    "nocheckcertificate": True,
    "extract_flat":       False,
    "http_headers": {
        "User-Agent":      USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    },
}
if os.path.exists("cookies.txt"):
    BASE_OPTS["cookiefile"] = "cookies.txt"


# ══════════════════════════════
#  PLATFORM DETECTION
# ══════════════════════════════
def is_youtube(url):   return "youtube.com" in url or "youtu.be" in url
def is_tiktok(url):    return "tiktok.com" in url
def is_instagram(url): return "instagram.com" in url


# ══════════════════════════════
#  OPTIONS
# ══════════════════════════════
def build_opts(url, filepath=None):
    """
    يبني إعدادات yt-dlp الكاملة.
    filepath=None  → استخراج معلومات فقط (بدون تحميل)
    filepath=...   → تحميل الملف
    """
    opts = dict(BASE_OPTS)
    opts["http_headers"] = dict(BASE_OPTS["http_headers"])

    # ── YouTube: تجاوز PO Token ──
    if is_youtube(url):
        opts["extractor_args"] = {
            "youtube": {
                # mediaconnect = الأحدث، لا يحتاج PO Token على السيرفرات
                "player_client": ["mediaconnect", "tv_embedded", "ios", "android", "mweb"],
            }
        }
        opts["geo_bypass"]             = True
        opts["allow_unplayable_formats"] = False
        opts["compat_opts"]             = {"no-youtube-unavailable-videos"}

    # ── TikTok / Instagram ──
    elif is_tiktok(url):
        opts["http_headers"]["Referer"] = "https://www.tiktok.com/"
    elif is_instagram(url):
        opts["http_headers"]["Referer"] = "https://www.instagram.com/"

    # ── عند الاستخراج فقط: حدد format بسيط يقلل الأخطاء ──
    if not filepath and is_youtube(url):
        opts["format"] = "best[height<=480]/best"

    # ── إذا طُلب التحميل أضف إعدادات format ──
    if filepath:
        if is_tiktok(url) or is_instagram(url):
            fmt = "best[ext=mp4]/best"
        elif is_youtube(url):
            # ✅ format بسيط يعمل مع جميع clients
            fmt = "best[height<=480]/best"
        else:
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
        })

    return opts


# ══════════════════════════════
#  BEST DIRECT URL (للزر الأخضر فقط عند YouTube)
# ══════════════════════════════
def get_direct_urls(info):
    """
    يحاول إيجاد روابط CDN مدمجة (video+audio).
    لـ TikTok/Instagram لن نستخدم هذا — نستخدم الملف المُحمَّل.
    """
    formats = info.get("formats", [])

    merged = [
        f for f in formats
        if f.get('vcodec') not in ('none', None)
        and f.get('acodec') not in ('none', None)
        and f.get('url')
    ]
    merged.sort(key=lambda f: f.get('height') or 0, reverse=True)

    if merged:
        return merged[0]['url'], merged[-1]['url']

    # YouTube: فيديو منفصل (بدون صوت) كـ fallback للتحميل
    video_only = [
        f for f in formats
        if f.get('vcodec') not in ('none', None) and f.get('url')
    ]
    video_only.sort(key=lambda f: f.get('height') or 0, reverse=True)

    if video_only:
        best = video_only[0]['url']
        low  = video_only[-1]['url'] if len(video_only) > 1 else best
        return best, low

    fb = info.get('url') or ""
    return fb, fb


# ══════════════════════════════
#  CLEANUP
# ══════════════════════════════
def cleanup_old_files():
    try:
        now = time.time()
        for f in os.listdir(DOWNLOAD_FOLDER):
            p = os.path.join(DOWNLOAD_FOLDER, f)
            if os.path.isfile(p) and now - os.path.getmtime(p) > 7200:
                os.remove(p)
    except Exception:
        pass


# ══════════════════════════════
#  ROUTES
# ══════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/download", methods=["POST"])
def download():
    cleanup_old_files()

    body = request.get_json()
    if not body or not body.get("url"):
        return jsonify({"error": "رابط غير صالح."}), 400

    url     = body["url"].strip()
    file_id = str(uuid.uuid4())
    fpath   = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    title     = "Video"
    thumbnail = "https://img.icons8.com/color/96/000000/video.png"
    dl_high   = ""
    dl_low    = ""

    # ══ PHASE 1: استخراج المعلومات فقط ══
    try:
        with yt_dlp.YoutubeDL(build_opts(url)) as ydl:
            info      = ydl.extract_info(url, download=False)
            title     = info.get("title", title)
            thumbnail = info.get("thumbnail", thumbnail)

            # لـ TikTok/Instagram لا نحتاج CDN URLs — سنستخدم الملف المُحمَّل
            if not is_tiktok(url) and not is_instagram(url):
                dl_high, dl_low = get_direct_urls(info)

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "403" in msg:
            return jsonify({"error": "المنصة رفضت الطلب (403) — تحتاج ملف cookies.txt"}), 500
        if "Private video" in msg:
            return jsonify({"error": "هذا الفيديو خاص."}), 500
        if "unavailable" in msg.lower():
            return jsonify({"error": "الفيديو غير متاح أو محذوف."}), 500
        if "Requested format" in msg or "not available" in msg.lower():
            return jsonify({"error": f"تعذّر استخراج الفيديو — {msg[-200:]}"}), 500
        return jsonify({"error": f"فشل الاستخراج: {msg[-300:]}"}), 500
    except Exception as e:
        return jsonify({"error": f"خطأ: {e}"}), 500

    # ══ PHASE 2: تحميل على السيرفر ══
    stream_url   = ""
    preview_type = "video"
    server_file  = None

    try:
        with yt_dlp.YoutubeDL(build_opts(url, fpath)) as ydl:
            ydl.download([url])

        # ابحث عن الملف
        for fname in os.listdir(DOWNLOAD_FOLDER):
            if fname.startswith(file_id):
                if fname.endswith(".mp4"):
                    server_file = fname
                    break
                server_file = fname  # أي امتداد

        if server_file:
            stream_url = f"/stream/{server_file}"
        else:
            raise FileNotFoundError("الملف لم يُوجد.")

    except Exception as e:
        preview_type = "error"
        print(f"[STREAM ERROR] {e}")

    # ══════════════════════════════════════════════════
    # ✅ الحل الجذري لـ TikTok/Instagram:
    #    نستخدم الملف المُحمَّل على السيرفر كرابط تحميل
    #    بدلاً من روابط CDN التي تحجبها Render
    # ══════════════════════════════════════════════════
    if server_file and (is_tiktok(url) or is_instagram(url)):
        dl_high = f"/stream/{server_file}?dl=1"
        dl_low  = dl_high

    # إذا فشل التحميل للـ YouTube أيضاً، استخدم الملف إن وُجد
    elif server_file and not dl_high:
        dl_high = f"/stream/{server_file}?dl=1"
        dl_low  = dl_high

    return jsonify({
        "title":             title,
        "thumbnail":         thumbnail,
        "stream_url":        stream_url,
        "preview_type":      preview_type,
        "download_url_high": dl_high,
        "download_url_low":  dl_low,
    })


# ══════════════════════════════
#  STREAM + DOWNLOAD ENDPOINT
#  يدعم Range Requests وأيضاً التحميل المباشر
# ══════════════════════════════
@app.route("/stream/<filename>")
def stream_video(filename):
    filename   = os.path.basename(filename)
    path       = os.path.join(DOWNLOAD_FOLDER, filename)
    force_dl   = request.args.get("dl") == "1"

    if not os.path.exists(path):
        abort(404)

    size = os.path.getsize(path)
    rng  = request.headers.get("Range")

    # ── تحميل مباشر (dl=1) ──
    if force_dl:
        return Response(
            _read_chunks(path),
            status=200,
            mimetype="video/mp4",
            headers={
                "Content-Length":      str(size),
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control":       "no-cache",
            }
        )

    # ── بث بدون Range ──
    if not rng:
        return Response(
            _read_chunks(path), status=200, mimetype="video/mp4",
            headers={
                "Content-Length": str(size),
                "Accept-Ranges":  "bytes",
                "Cache-Control":  "no-cache",
            }
        )

    # ── بث مع Range (Partial Content 206) ──
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
        _read_chunks(path, b1, ln), status=206, mimetype="video/mp4",
        headers={
            "Content-Range":  f"bytes {b1}-{b2}/{size}",
            "Accept-Ranges":  "bytes",
            "Content-Length": str(ln),
            "Cache-Control":  "no-cache",
        }
    )


def _read_chunks(path, start=0, length=None):
    CHUNK = 1024 * 1024
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
