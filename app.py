import os
import re
import uuid
import time
import subprocess
import sys
import urllib.request
from flask import Flask, render_template, request, jsonify, Response, abort
import yt_dlp
import imageio_ffmpeg

# ✅ تحديث yt-dlp تلقائياً عند كل بدء تشغيل
try:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "-q"],
        check=True, timeout=120
    )
    print("[INFO] yt-dlp updated.")
except Exception as e:
    print(f"[WARN] yt-dlp update failed: {e}")

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


# ══════════════════════════════════════
#  PLATFORM DETECTION
# ══════════════════════════════════════
def is_youtube(url):
    return "youtube.com" in url or "youtu.be" in url

def is_youtube_live(url):
    return "youtube.com/live/" in url or "youtube.com/watch" in url

def is_tiktok(url):
    return "tiktok.com" in url

def is_instagram(url):
    return "instagram.com" in url


# ══════════════════════════════════════
#  BUILD OPTIONS PER PLATFORM
# ══════════════════════════════════════
def get_extract_opts(url):
    opts = dict(BASE_OPTS)
    opts["http_headers"] = dict(BASE_OPTS["http_headers"])

    if is_tiktok(url):
        opts["http_headers"]["Referer"] = "https://www.tiktok.com/"

    elif is_instagram(url):
        opts["http_headers"]["Referer"] = "https://www.instagram.com/"

    elif is_youtube(url):
        # ✅ حل مشكلة PO Token في YouTube
        # يجرّب جميع player clients حتى يجد واحداً يعمل
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["ios", "android", "web", "mweb"],
                "skip": ["hls", "dash"],
            }
        }

    return opts


def get_stream_opts(url, filepath):
    opts = get_extract_opts(url)

    if is_tiktok(url) or is_instagram(url):
        fmt = "best[ext=mp4]/best"
    elif is_youtube(url):
        # ✅ YouTube: بدون تحديد ext حتى يعمل مع ios/android clients
        fmt = (
            "bestvideo[height<=480]+bestaudio"
            "/bestvideo[height<=480]+bestaudio[ext=m4a]"
            "/best[height<=480]"
            "/best"
        )
        # ✅ أزل skip لأننا نحتاج hls أحياناً للتحميل
        if "extractor_args" in opts:
            opts["extractor_args"]["youtube"].pop("skip", None)
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


# ══════════════════════════════════════
#  SMART URL EXTRACTOR
#  يضمن دائماً إرجاع رابطين صالحين
# ══════════════════════════════════════
def get_all_download_urls(info, original_url):
    formats = info.get("formats", [])

    # ── الصيغ المدمجة (video + audio معاً) ──
    merged = [
        f for f in formats
        if f.get('vcodec') not in ('none', None)
        and f.get('acodec') not in ('none', None)
        and f.get('url')
    ]
    merged.sort(key=lambda f: (f.get('height') or 0), reverse=True)

    if merged:
        best = merged[0]['url']
        low  = merged[-1]['url']

        # ✅ TikTok/Instagram: روابط CDN تحتاج proxy
        if is_tiktok(original_url) or is_instagram(original_url):
            best = f"/proxy-dl?url={urllib.parse.quote(best)}&platform=tiktok"
            low  = best
        return {"best": best, "low": low}

    # ── YouTube: فيديو وصوت منفصلان — خذ أفضل فيديو فقط ──
    video_only = [
        f for f in formats
        if f.get('vcodec') not in ('none', None) and f.get('url')
    ]
    video_only.sort(key=lambda f: (f.get('height') or 0), reverse=True)

    if video_only:
        best = video_only[0]['url']
        low  = video_only[-1]['url'] if len(video_only) > 1 else best
        return {"best": best, "low": low}

    fallback = info.get('url') or ""
    return {"best": fallback, "low": fallback}


def cleanup_old_files():
    try:
        now = time.time()
        for fname in os.listdir(DOWNLOAD_FOLDER):
            fpath = os.path.join(DOWNLOAD_FOLDER, fname)
            if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 7200:
                os.remove(fpath)
    except Exception:
        pass


# ══════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════
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
    dl_best   = ""
    dl_low    = ""

    # ══ PHASE 1: استخراج المعلومات ══
    try:
        extract_opts = get_extract_opts(url)
        with yt_dlp.YoutubeDL(extract_opts) as ydl:
            info      = ydl.extract_info(url, download=False)
            title     = info.get("title", title)
            thumbnail = info.get("thumbnail", thumbnail)
            urls      = get_all_download_urls(info, url)
            dl_best   = urls["best"] or ""
            dl_low    = urls["low"]  or ""

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "403" in msg:
            return jsonify({"error": "المنصة رفضت الطلب (403). قد تحتاج ملف cookies.txt"}), 500
        if "Private video" in msg:
            return jsonify({"error": "هذا الفيديو خاص."}), 500
        if "unavailable" in msg.lower():
            return jsonify({"error": "الفيديو غير متاح أو محذوف."}), 500
        if "Requested format is not available" in msg:
            return jsonify({"error": "الصيغة غير متاحة لهذا الفيديو. جرّب رابطاً آخر أو تحقق أن الفيديو متاح للعموم."}), 500
        return jsonify({"error": f"فشل الاستخراج: {msg}"}), 500
    except Exception as e:
        return jsonify({"error": f"خطأ: {str(e)}"}), 500

    # ══ PHASE 2: تحميل للبث ══
    stream_url   = ""
    preview_type = "video"

    try:
        with yt_dlp.YoutubeDL(get_stream_opts(url, filepath)) as ydl:
            ydl.download([url])

        final = None
        for fname in os.listdir(DOWNLOAD_FOLDER):
            if fname.startswith(file_id):
                if fname.endswith(".mp4"):
                    final = fname
                    break
                final = fname

        if final:
            stream_url = f"/stream/{final}"
        else:
            raise FileNotFoundError("الملف لم يُوجد.")

    except Exception as e:
        preview_type = "error"
        print(f"[STREAM ERROR] {e}")

    return jsonify({
        "title":             title,
        "thumbnail":         thumbnail,
        "stream_url":        stream_url,
        "preview_type":      preview_type,
        "download_url_high": dl_best,
        "download_url_low":  dl_low,
    })


# ══════════════════════════════════════
#  ✅ PROXY ENDPOINT — لحل مشكلة TikTok CDN
#  يبث الفيديو عبر السيرفر مع headers صحيحة
# ══════════════════════════════════════
import urllib.parse

@app.route("/proxy-dl")
def proxy_download():
    import urllib.request as ur

    raw_url  = request.args.get("url", "")
    platform = request.args.get("platform", "")

    if not raw_url:
        abort(400)

    # headers حسب المنصة
    headers = {
        "User-Agent":      USER_AGENT,
        "Accept":          "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if platform == "tiktok":
        headers["Referer"] = "https://www.tiktok.com/"
    elif platform == "instagram":
        headers["Referer"] = "https://www.instagram.com/"

    try:
        req = ur.Request(raw_url, headers=headers)
        remote = ur.urlopen(req, timeout=30)
        content_type = remote.headers.get("Content-Type", "video/mp4")
        content_len  = remote.headers.get("Content-Length", "")

        resp_headers = {
            "Content-Type":        content_type,
            "Accept-Ranges":       "bytes",
            "Cache-Control":       "no-cache",
            "Content-Disposition": "attachment; filename=video.mp4",
        }
        if content_len:
            resp_headers["Content-Length"] = content_len

        def stream():
            while True:
                chunk = remote.read(1024 * 64)
                if not chunk:
                    break
                yield chunk

        return Response(stream(), status=200, headers=resp_headers)

    except Exception as e:
        print(f"[PROXY ERROR] {e}")
        abort(502)


# ══════════════════════════════════════
#  STREAM — Range Requests
# ══════════════════════════════════════
@app.route("/stream/<filename>")
def stream_video(filename):
    filename = os.path.basename(filename)
    path     = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(path):
        abort(404)

    size = os.path.getsize(path)
    rng  = request.headers.get("Range")

    if not rng:
        return Response(
            _read_chunks(path), status=200, mimetype="video/mp4",
            headers={"Content-Length": str(size),
                     "Accept-Ranges":  "bytes",
                     "Cache-Control":  "no-cache"}
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
        _read_chunks(path, b1, ln), status=206, mimetype="video/mp4",
        headers={"Content-Range":  f"bytes {b1}-{b2}/{size}",
                 "Accept-Ranges":  "bytes",
                 "Content-Length": str(ln),
                 "Cache-Control":  "no-cache"}
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
