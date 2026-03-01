import os
import uuid
from flask import Flask, render_template, request, jsonify, send_file, Response
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
}

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "Invalid URL"}), 400

    file_id = str(uuid.uuid4())
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    opts = dict(YDL_OPTS)
    opts.update({
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": filepath,
        "merge_output_format": "mp4",
    })

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        final_file = None
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(file_id):
                final_file = f
                break

        if not final_file:
            return jsonify({"error": "Download failed"}), 500

        return jsonify({
            "stream_url": f"/stream/{final_file}",
            "download_url": f"/file/{final_file}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/stream/<filename>")
def stream_video(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)

    if not os.path.exists(filepath):
        return "File not found", 404

    range_header = request.headers.get("Range", None)
    if not range_header:
        return send_file(filepath, mimetype="video/mp4")

    size = os.path.getsize(filepath)
    byte1, byte2 = 0, None

    match = range_header.replace("bytes=", "").split("-")
    if match[0]:
        byte1 = int(match[0])
    if len(match) > 1 and match[1]:
        byte2 = int(match[1])

    byte2 = byte2 if byte2 is not None else size - 1
    length = byte2 - byte1 + 1

    with open(filepath, "rb") as f:
        f.seek(byte1)
        data = f.read(length)

    response = Response(data, 206, mimetype="video/mp4")
    response.headers.add("Content-Range", f"bytes {byte1}-{byte2}/{size}")
    response.headers.add("Accept-Ranges", "bytes")
    response.headers.add("Content-Length", str(length))

    return response


@app.route("/file/<filename>")
def download_file(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)

    if not os.path.exists(filepath):
        return "File not found", 404

    return send_file(filepath, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
