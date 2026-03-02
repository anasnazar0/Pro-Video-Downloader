import os
import uuid
import time
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Base options for extracting information without downloading
EXTRACT_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "cookiefile": "cookies.txt",
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
        # Phase 1: Metadata and Direct Link Extraction (Failsafe Phase)
        # This phase only extracts information and does NOT download the video.
        best_download_url = None
        fallback_url = None
        
        with yt_dlp.YoutubeDL(EXTRACT_OPTS) as ydl_info:
            info = ydl_info.extract_info(url, download=False)
            title = info.get("title", "Video Ready")
            thumbnail = info.get("thumbnail")
            fallback_url = info.get('url')
            
            formats = info.get('formats', [])
            for f in reversed(formats):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                    best_download_url = f.get('url')
                    break
            
            if not best_download_url:
                best_download_url = fallback_url

        # Phase 2: Server Download for Streaming (Isolated Phase)
        # If this phase fails, the app will NOT crash. It will just skip streaming.
        stream_opts = dict(EXTRACT_OPTS)
        stream_opts.update({
            "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            "outtmpl": filepath,
            "merge_output_format": "mp4"
        })

        stream_url = ""
        preview_type = "video"

        try:
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
                raise Exception("Streaming file was not created.")

        except Exception as stream_error:
            # Silently catch the streaming error (e.g., missing FFmpeg or format unavailable)
            # The frontend will be instructed to show an error only in the player area.
            print(f"Streaming preparation failed: {stream_error}")
            preview_type = "error"
            stream_url = ""

        # Phase 3: Return the unified response
        # Even if streaming failed, download links are guaranteed to be sent.
        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "stream_url": stream_url,
            "preview_type": preview_type,
            "download_url_high": best_download_url,
            "download_url_low": fallback_url
        })

    except Exception as e:
        # This exception only triggers if Phase 1 (Metadata extraction) fails entirely.
        return jsonify({"error": f"Failed to extract video information: {str(e)}"}), 500

@app.route("/stream/<filename>")
def stream_video(filename):
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return "File not found or expired.", 404
    return send_file(path, mimetype="video/mp4", conditional=True)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
