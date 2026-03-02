import os
import uuid
import time
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import imageio_ffmpeg

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# 🛠️ Extract the path for the local FFmpeg binary to bypass Render limitations
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# Options for Phase 1: Pure Extraction ONLY (No downloading)
EXTRACT_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "cookiefile": "cookies.txt",
    "extract_flat": False,
}

def cleanup_old_files():
    """Removes downloaded files older than 30 minutes to save server space."""
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
    # PHASE 1: EXACT EXTRACTION (DIRECT LINK ONLY)
    # ==========================================
    try:
        with yt_dlp.YoutubeDL(EXTRACT_OPTS) as ydl_info:
            info = ydl_info.extract_info(url, download=False)
            title = info.get("title", title)
            thumbnail = info.get("thumbnail", thumbnail)
            fallback_url = info.get('url')
            
            # Find the best quality pre-merged direct link for the download button
            formats = info.get('formats', [])
            for f in reversed(formats):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                    best_download_url = f.get('url')
                    break
            
            if not best_download_url:
                best_download_url = fallback_url
    except Exception as e:
        return jsonify({"error": f"Failed to fetch video details: {str(e)}"}), 500


    # ==========================================
    # PHASE 2: ATTEMPT SERVER DOWNLOAD FOR STREAMING (POWERED BY FFMPEG)
    # ==========================================
    stream_url = ""
    preview_type = "video"

    try:
        # Options for Phase 2: Downloading and merging with FFmpeg
        stream_opts = dict(EXTRACT_OPTS)
        stream_opts.update({
            "ffmpeg_location": FFMPEG_PATH, # 🚀 This fixes the hidden format error!
            "format": "bv*[height<=480]+ba/b[height<=480]/best",
            "outtmpl": filepath,
            "merge_output_format": "mp4"
        })

        # Download the file to the server for fast streaming
        with yt_dlp.YoutubeDL(stream_opts) as ydl_down:
            ydl_down.download([url])

        final_file = None
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(file_id):
                final_file = f
                break
        
        if final_file:
            stream_url = f"/stream/{final_file}"
        else:
            raise Exception("File merging failed silently.")

    except Exception as stream_error:
        # If Phase 2 still fails (e.g., YouTube blocks the IP), activate the graceful fallback
        preview_type = "error"
        stream_url = ""
        print(f"Streaming phase canceled: {stream_error}")

    # ==========================================
    # PHASE 3: RETURN UNIFIED RESPONSE
    # ==========================================
    return jsonify({
        "title": title,
        "thumbnail": thumbnail,
        "stream_url": stream_url,
        "preview_type": preview_type,
        "download_url_high": best_download_url,
        "download_url_low": fallback_url
    })

@app.route("/stream/<filename>")
def stream_video(filename):
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return "File not found.", 404
    return send_file(path, mimetype="video/mp4", conditional=True)

if __name__ == "__main__":
    app.run(debug=True, port=5000)

