import os
import re
import uuid
import time
from flask import Flask, render_template, request, jsonify, Response, abort
import yt_dlp
import imageio_ffmpeg


app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# ✅ بدون "format" هنا — فقط للاستخراج
EXTRACT_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "extract_flat": False,
}

if os.path.exists("cookies.txt"):
    EXTRACT_OPTS["cookiefile"] = "cookies.txt"


def get_best_download_url(formats):
    """يجلب أفضل رابط مباشر (فيديو + صوت مدمجان)."""
    # الأولوية 1: mp4 مدمج
    for f in reversed(formats):
        if (f.get('vcodec') not in ('none', None) and
                f.get('acodec') not in ('none', None) and
                f.get('ext') == 'mp4' and f.get('url')):
            return f.get('url')
    # الأولوية 2: أي صيغة مدمجة
    for f in reversed(formats):
        if (f.get('vcodec') not in ('none', None) and
                f.get('acodec') not in ('none', None) and f.get('url')):
            return f.get('url')
    return None


def cleanup_old_files():
    try:
        now = time.time()
        for f in os.listdir(DOWNLOAD_FOLDER):
            path = os.path.join(DOWNLOAD_FOLDER, f)
            if os.path.isfile(path) and now - os.path.getmtime(path) > 7200:
                os.remove(path)
    except Exception:
        pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/download", methods=["POST"])
def download():
    cleanup_old_files()

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data received."}), 400

    url = data.get("url")
    if not url:
        return jsonify({"error": "Invalid URL provided."}), 400

    file_id  = str(uuid.uuid4())
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    best_download_url = None
    fallback_url      = None
    title             = "Video Ready"
    thumbnail         = "https://img.icons8.com/color/96/000000/video.png"

    # ── PHASE 1: استخراج المعلومات فقط ──
    try:
        with yt_dlp.YoutubeDL(EXTRACT_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            title        = info.get("title", title)
            thumbnail    = info.get("thumbnail", thumbnail)
            fallback_url = info.get("url")
            formats      = info.get("formats", [])
            best_download_url = get_best_download_url(formats)
            if not best_download_url:
                best_download_url = fallback_url
    except Exception as e:
        return jsonify({"error": f"Failed to fetch video details: {str(e)}"}), 500

    # ── PHASE 2: تحميل الفيديو على السيرفر للبث ──
    stream_url   = ""
    preview_type = "video"

    try:
        stream_opts = dict(EXTRACT_OPTS)
        stream_opts.update({
            "ffmpeg_location": FFMPEG_PATH,
            "format": (
                "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]"
                "/bestvideo[height<=480]+bestaudio"
                "/best[height<=480]"
                "/best"
            ),
            "outtmpl": filepath,
            "merge_output_format": "mp4",
        })

        with yt_dlp.YoutubeDL(stream_opts) as ydl_down:
            ydl_down.download([url])

        final_file = None
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(file_id) and f.endswith(".mp4"):
                final_file = f
                break
        if not final_file:
            for f in os.listdir(DOWNLOAD_FOLDER):
                if f.startswith(file_id):
                    final_file = f
                    break

        if final_file:
            stream_url = f"/stream/{final_file}"
        else:
            raise Exception("File not found after download.")

    except Exception as e:
        preview_type = "error"
        stream_url   = ""
        print(f"[STREAM ERROR] {e}")

    return jsonify({
        "title":             title,
        "thumbnail":         thumbnail,
        "stream_url":        stream_url,
        "preview_type":      preview_type,
        "download_url_high": best_download_url,
        "download_url_low":  fallback_url,
    })


# ── STREAM مع دعم Range Requests الكامل ──
@app.route("/stream/<filename>")
def stream_video(filename):
    filename = os.path.basename(filename)
    path     = os.path.join(DOWNLOAD_FOLDER, filename)

    if not os.path.exists(path):
        abort(404)

    file_size    = os.path.getsize(path)
    range_header = request.headers.get("Range")

    if not range_header:
        def full_stream():
            with open(path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk
        return Response(full_stream(), status=200, mimetype="video/mp4",
                        headers={"Content-Length": str(file_size),
                                 "Accept-Ranges":  "bytes",
                                 "Cache-Control":  "no-cache"})

    match = re.search(r"bytes=(\d+)-(\d*)", range_header)
    if not match:
        abort(416)

    byte1 = int(match.group(1))
    byte2 = int(match.group(2)) if match.group(2) else file_size - 1
    byte2 = min(byte2, file_size - 1)
    if byte1 > byte2:
        abort(416)

    length = byte2 - byte1 + 1

    def partial_stream():
        with open(path, "rb") as f:
            f.seek(byte1)
            remaining = length
            while remaining > 0:
                data = f.read(min(1024 * 1024, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return Response(partial_stream(), status=206, mimetype="video/mp4",
                    headers={"Content-Range":  f"bytes {byte1}-{byte2}/{file_size}",
                             "Accept-Ranges":  "bytes",
                             "Content-Length": str(length),
                             "Cache-Control":  "no-cache"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
