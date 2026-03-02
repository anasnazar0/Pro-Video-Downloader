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

EXTRACT_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "extract_flat": False,
}

# أضف الكوكيز فقط إذا كان الملف موجوداً
if os.path.exists("cookies.txt"):
    EXTRACT_OPTS["cookiefile"] = "cookies.txt"


def cleanup_old_files():
    """يحذف الملفات القديمة التي مضى عليها أكثر من ساعتين."""
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

    file_id = str(uuid.uuid4())
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    best_download_url = None
    fallback_url = None
    title = "Video Ready"
    thumbnail = "https://img.icons8.com/color/96/000000/video.png"

    # ==========================================
    # PHASE 1: استخراج المعلومات فقط
    # ==========================================
    try:
        with yt_dlp.YoutubeDL(EXTRACT_OPTS) as ydl_info:
            info = ydl_info.extract_info(url, download=False)
            title = info.get("title", title)
            thumbnail = info.get("thumbnail", thumbnail)
            fallback_url = info.get('url')

            formats = info.get('formats', [])
            for f in reversed(formats):
                if (f.get('vcodec') != 'none' and
                        f.get('acodec') != 'none' and
                        f.get('ext') == 'mp4'):
                    best_download_url = f.get('url')
                    break

            if not best_download_url:
                best_download_url = fallback_url

    except Exception as e:
        return jsonify({"error": f"Failed to fetch video details: {str(e)}"}), 500

    # ==========================================
    # PHASE 2: تحميل الفيديو على السيرفر للبث
    # ==========================================
    stream_url = ""
    preview_type = "video"

    try:
        stream_opts = dict(EXTRACT_OPTS)
        stream_opts.update({
            "ffmpeg_location": FFMPEG_PATH,
            "format": "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]/best[height<=480]/best",
            "outtmpl": filepath,
            "merge_output_format": "mp4",
            "postprocessors": [{
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }],
        })

        with yt_dlp.YoutubeDL(stream_opts) as ydl_down:
            ydl_down.download([url])

        # البحث عن الملف الذي تم تحميله
        final_file = None
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(file_id) and f.endswith(".mp4"):
                final_file = f
                break

        # إذا لم يجد .mp4 ابحث عن أي امتداد
        if not final_file:
            for f in os.listdir(DOWNLOAD_FOLDER):
                if f.startswith(file_id):
                    final_file = f
                    break

        if final_file:
            stream_url = f"/stream/{final_file}"
        else:
            raise Exception("File not found after download.")

    except Exception as stream_error:
        preview_type = "error"
        stream_url = ""
        print(f"[STREAM ERROR] {stream_error}")

    return jsonify({
        "title": title,
        "thumbnail": thumbnail,
        "stream_url": stream_url,
        "preview_type": preview_type,
        "download_url_high": best_download_url,
        "download_url_low": fallback_url
    })


# ==========================================
# ✅ STREAM ENDPOINT - مع دعم Range Requests الكامل
# ==========================================
@app.route("/stream/<filename>")
def stream_video(filename):
    # تأمين الاسم من أي هجوم Path Traversal
    filename = os.path.basename(filename)
    path = os.path.join(DOWNLOAD_FOLDER, filename)

    if not os.path.exists(path):
        abort(404)

    file_size = os.path.getsize(path)
    range_header = request.headers.get("Range")

    # --- بدون Range Header: إرسال الملف كاملاً ---
    if not range_header:
        def generate_full():
            with open(path, "rb") as f:
                while chunk := f.read(1024 * 1024):  # 1MB chunks
                    yield chunk

        return Response(
            generate_full(),
            status=200,
            mimetype="video/mp4",
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache",
            }
        )

    # --- مع Range Header: إرسال جزء محدد (Partial Content 206) ---
    match = re.search(r"bytes=(\d+)-(\d*)", range_header)
    if not match:
        abort(416)  # Range Not Satisfiable

    byte1 = int(match.group(1))
    byte2 = int(match.group(2)) if match.group(2) else file_size - 1

    # التأكد من أن القيم منطقية
    byte2 = min(byte2, file_size - 1)
    if byte1 > byte2:
        abort(416)

    length = byte2 - byte1 + 1

    def generate_chunk():
        with open(path, "rb") as f:
            f.seek(byte1)
            remaining = length
            while remaining > 0:
                chunk_size = min(1024 * 1024, remaining)  # 1MB max chunk
                data = f.read(chunk_size)
                if not data:
                    break
                remaining -= len(data)
                yield data

    return Response(
        generate_chunk(),
        status=206,
        mimetype="video/mp4",
        headers={
            "Content-Range": f"bytes {byte1}-{byte2}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Cache-Control": "no-cache",
        }
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
