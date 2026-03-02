import os
import uuid
import time
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Base options for yt-dlp to ensure smooth extraction
YDL_OPTS = {
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
    # Trigger cleanup process on every new download request
    cleanup_old_files()

    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "Invalid URL provided."}), 400

    file_id = str(uuid.uuid4())
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    try:
        # Step 1: Extract basic video information
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl_info:
            info = ydl_info.extract_info(url, download=False)
            title = info.get("title", "Video Ready")
            thumbnail = info.get("thumbnail")

        stream_opts = dict(YDL_OPTS)
        
        # Step 2: Domain-Based Routing to prevent FFmpeg crashes on Render
        if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
            # YouTube Logic: Target pre-merged formats directly (18=360p, 22=720p)
            # Avoid using 'merge_output_format' to bypass the need for FFmpeg
            stream_opts.update({
                "format": "18/22/b",
                "outtmpl": filepath
            })
        else:
            # Universal Logic: Flexible fetching for TikTok, Facebook, etc.
            stream_opts.update({
                "format": "bv*[height<=480]+ba/b[height<=480]/best",
                "outtmpl": filepath,
                "merge_output_format": "mp4"
            })

        # Execute the actual download
        with yt_dlp.YoutubeDL(stream_opts) as ydl_down:
            ydl_down.download([url])

        # Locate the downloaded file in the folder
        final_file = None
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(file_id):
                final_file = f
                break

        if not final_file:
            return jsonify({"error": "Failed to process the video."}), 500

        # Return the response to the frontend
        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "stream_url": f"/stream/{final_file}",
            "download_url_high": f"/file/{final_file}",
            "download_url_low": f"/file/{final_file}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stream/<filename>")
def stream_video(filename):
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return "File not found or expired.", 404
    # 'conditional=True' allows proper video streaming and seeking
    return send_file(path, mimetype="video/mp4", conditional=True)

@app.route("/file/<filename>")
def download_file(filename):
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return "File not found or expired.", 404
    return send_file(path, as_attachment=True, download_name="Universal_Video.mp4")

@app.route("/version")
def version():
    """Route to easily check the current installed version of yt-dlp."""
    import yt_dlp
    return {"yt_dlp_version": yt_dlp.version.__version__}

if __name__ == "__main__":
    app.run(debug=True, port=5000)
