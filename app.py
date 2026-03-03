import os
import re
import uuid
import time
import subprocess
import sys
from flask import Flask, render_template, request, jsonify, Response, abort
import yt_dlp
import imageio_ffmpeg

# ✅ تحديث yt-dlp تلقائياً
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


def is_tiktok(url):
    return "tiktok.com" in url or "vm.tiktok.com" in url


def get_extract_opts(url):
    opts = dict(BASE_OPTS)
    opts["http_headers"] = dict(BASE_OPTS["http_headers"])
    if is_tiktok(url):
        opts["http_headers"]["Referer"] = "https://www.tiktok.com/"
    return opts


def get_stream_opts(url, filepath):
    opts = get_extract_opts(url)
    fmt = (
        "best[ext=mp4]/best"
        if is_tiktok(url)
        else "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
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


def get_all_download_urls(info):
    """
    يُرجع دائماً رابطين على الأقل (best, low).
    يضمن عدم إرجاع None حتى لو YouTube يفصل الصوت عن الفيديو.
    """
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
        best_url = merged[0]['url']
        low_url  = merged[-1]['url']
        return {"best": best_url, "low": low_url}

    # ── YouTube: روابط منفصلة — خذ أفضل فيديو كـ fallback ──
    video_only = [
        f for f in formats
        if f.get('vcodec') not in ('none', None) and f.get('url')
    ]
    video_only.sort(key=lambda f: (f.get('height') or 0), reverse=True)

    if video_only:
        return {
            "best": video_only[0]['url'],
            "low":  video_only[-1]['url'] if len(video_only) > 1 else video_only[0]['url'],
        }

    # ── آخر حل ──
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

    # ══ PHASE 1: استخراج ══
    try:
        with yt_dlp.YoutubeDL(get_extract_opts(url)) as ydl:
            info      = ydl.extract_info(url, download=False)
            title     = info.get("title", title)
            thumbnail = info.get("thumbnail", thumbnail)
            urls      = get_all_download_urls(info)
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
