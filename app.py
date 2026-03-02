import os
import uuid
import time
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import imageio_ffmpeg

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# THE GENIUS FIX: Extract the internal static FFmpeg path provided by imageio_ffmpeg
# This bypasses Render's lack of FFmpeg installation!
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# Base options for yt-dlp, now empowered with local FFmpeg
YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "cookiefile": "cookies.txt",
    "ffmpeg_location": FFMPEG_PATH,  # Feeding the static FFmpeg binary to yt-dlp
}

def cleanup_old_files():
    """Removes downloaded files older than 30 minutes to free up server space."""
    try:
        now = time.time()
        for f in os.listdir(DOWNLOAD_FOLDER):
            path = os.path.join(DOWNLOAD_FOLDER, f)
            if os.path.isfile(path) and now - os.path.getmtime(path) > 1800:
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
    url = data.get("url")

    if not url:
        return jsonify({"error": "Invalid URL provided."}), 400

    file_id = str(uuid.uuid4())
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    try:
        # Step 1: Extract basic video information and direct High-Q URL if possible
        best_download_url = None
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl_info:
            info = ydl_info.extract_info(url, download=False)
            title = info.get("title", "Video Ready")
            thumbnail = info.get("thumbnail")
            
            formats = info.get('formats', [])
            for f in reversed(formats):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                    best_download_url = f.get('url')
                    break
            
            if not best_download_url:
                best_download_url = info.get('url')

        # Step 2: Unified Download Logic for ALL platforms
        # Now that we have FFmpeg, we can confidently ask for separated video and audio
        # and merge them into MP4. We limit height to 480p to protect Render's RAM.
        stream_opts = dict(YDL_OPTS)
        stream_opts.update({
            "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            "outtmpl": filepath,
            "merge_output_format": "mp4"
        })

        # Execute the actual download and merge
        with yt_dlp.YoutubeDL(stream_opts) as ydl_down:
            ydl_down.download([url])

        final_file = None
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(file_id):
                final_file = f
                break

        if not final_file:
            return jsonify({"error": "Failed to process the video."}), 500

        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "stream_url": f"/stream/{final_file}",
            "download_url_high": best_download_url if best_download_url else f"/file/{final_file}",
            "download_url_low": f"/file/{final_file}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stream/<filename>")
def stream_video(filename):
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return "File not found or expired.", 404
    return send_file(path, mimetype="video/mp4", conditional=True)

@app.route("/file/<filename>")
def download_file(filename):
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return "File not found or expired.", 404
    return send_file(path, as_attachment=True, download_name="Universal_Video.mp4")

@app.route("/version")
def version():
    import yt_dlp
    return {"yt_dlp_version": yt_dlp.version.__version__}

if __name__ == "__main__":
    app.run(debug=True, port=5000)
