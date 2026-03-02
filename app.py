import os
import uuid
import time
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import imageio_ffmpeg

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Inject local FFmpeg to bypass Render limitations
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# Base options for yt-dlp
YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "cookiefile": "cookies.txt",
    "ffmpeg_location": FFMPEG_PATH,
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
        # Step 1: Extract basic video metadata and direct High-Q URL
        best_download_url = None
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl_info:
            info = ydl_info.extract_info(url, download=False)
            title = info.get("title", "Video Ready")
            thumbnail = info.get("thumbnail")
            video_id = info.get("id")
            
            formats = info.get('formats', [])
            for f in reversed(formats):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                    best_download_url = f.get('url')
                    break
            
            if not best_download_url:
                best_download_url = info.get('url')

        # Step 2: Attempt standard server download with FFmpeg
        stream_opts = dict(YDL_OPTS)
        stream_opts.update({
            "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            "outtmpl": filepath,
            "merge_output_format": "mp4"
        })

        preview_type = "video"
        stream_url = ""

        try:
            # 🚀 Primary Attempt: Download and merge on the server
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
                raise Exception("File missing after download process.")

        except Exception as internal_error:
            # 🛡️ THE AUTO-FALLBACK SYSTEM
            # If server blocks the download/merge, silently switch to Iframe mode for YouTube
            if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
                stream_url = f"https://www.youtube.com/embed/{video_id}"
                preview_type = "iframe"
            else:
                # If it's not YouTube, report the error to the user
                return jsonify({"error": f"Failed to process media: {str(internal_error)}"}), 500

        # Step 3: Return the final robust response
        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "stream_url": stream_url,
            "preview_type": preview_type,
            "download_url_high": best_download_url if best_download_url else stream_url,
            "download_url_low": best_download_url if best_download_url else stream_url
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
