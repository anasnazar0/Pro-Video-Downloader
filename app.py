import os, re, uuid, time, subprocess, sys, json
import urllib.request
from flask import Flask, render_template, request, jsonify, Response, abort
import yt_dlp, imageio_ffmpeg

# تحديث yt-dlp تلقائياً
try:
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "-q"],
                   check=True, timeout=120)
    print("[INFO] yt-dlp updated.")
except Exception as e:
    print(f"[WARN] {e}")

app = Flask(__name__)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
COOKIES = "cookies.txt" if os.path.exists("cookies.txt") else None


# ════════════════════════════════
#  كشف المنصة
# ════════════════════════════════
def is_youtube(url):   return "youtube.com" in url or "youtu.be" in url
def is_tiktok(url):    return "tiktok.com" in url
def is_instagram(url): return "instagram.com" in url

def extract_yt_id(url):
    m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


# ════════════════════════════════
#  بناء الإعدادات
# ════════════════════════════════
def build_opts(url, filepath=None):
    """
    filepath=None  → استخراج معلومات فقط
    filepath=path  → تحميل الفيديو
    """
    opts = {
        "quiet":              True,
        "no_warnings":        True,
        "nocheckcertificate": True,
        "check_formats":      False,
        "http_headers": {
            "User-Agent":      USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    if COOKIES:
        opts["cookiefile"] = COOKIES

    # ── إعدادات حسب المنصة ──
    if is_youtube(url):
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["tv_embedded", "ios", "android", "mweb"],
            }
        }
        opts["geo_bypass"] = True

    elif is_tiktok(url):
        opts["http_headers"]["Referer"] = "https://www.tiktok.com/"

    elif is_instagram(url):
        opts["http_headers"]["Referer"] = "https://www.instagram.com/"

    # ── إضافة إعدادات التحميل إذا طُلب ──
    if filepath:
        if is_tiktok(url) or is_instagram(url):
            fmt = "best[ext=mp4]/best"
        else:
            fmt = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"

        opts.update({
            "ffmpeg_location":     FFMPEG_PATH,
            "format":              fmt,
            "outtmpl":             filepath,
            "merge_output_format": "mp4",
            "retries":             3,
            "fragment_retries":    3,
        })

    return opts


# ════════════════════════════════
#  مساعدات
# ════════════════════════════════
def find_file(file_id):
    """يجد الملف المُحمَّل."""
    for f in os.listdir(DOWNLOAD_FOLDER):
        if f.startswith(file_id) and f.endswith(".mp4"):
            return f
    for f in os.listdir(DOWNLOAD_FOLDER):
        if f.startswith(file_id):
            return f
    return None


def cleanup_old_files():
    try:
        now = time.time()
        for f in os.listdir(DOWNLOAD_FOLDER):
            p = os.path.join(DOWNLOAD_FOLDER, f)
            if os.path.isfile(p) and now - os.path.getmtime(p) > 7200:
                os.remove(p)
    except Exception:
        pass


# ════════════════════════════════
#  ROUTES
# ════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")



@app.route("/download", methods=["POST"])
def download():
    cleanup_old_files()
    body = request.get_json()
    if not body or not body.get("url"):
        return jsonify({"error": "رابط غير صالح."}), 400
    url = body["url"].strip()

    # YouTube: embed iframe - no server download needed
    if is_youtube(url):
        vid_id = extract_yt_id(url)
        if not vid_id:
            return jsonify({"error": "تعذّر استخراج معرّف الفيديو."}), 400
        title     = "YouTube Video"
        thumbnail = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
        try:
            oembed_url = (f"https://www.youtube.com/oembed"
                          f"?url=https://www.youtube.com/watch?v={vid_id}&format=json")
            req = urllib.request.Request(oembed_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as r:
                data      = json.loads(r.read())
                title     = data.get("title", title)
                thumbnail = data.get("thumbnail_url", thumbnail)
        except Exception:
            pass
        return jsonify({
            "title":             title,
            "thumbnail":         thumbnail,
            "preview_type":      "youtube_embed",
            "embed_url":         f"https://www.youtube.com/embed/{vid_id}?autoplay=1&rel=0",
            "stream_url":        "",
            "download_url_high": f"https://www.youtube.com/watch?v={vid_id}",
            "download_url_low":  f"https://youtu.be/{vid_id}",
        })

    # TikTok / Instagram / others: download to server
    file_id = str(uuid.uuid4())
    fpath   = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")
    title     = "Video"
    thumbnail = "https://img.icons8.com/color/96/000000/video.png"
    try:
        with yt_dlp.YoutubeDL(build_opts(url)) as ydl:
            info      = ydl.extract_info(url, download=False)
            title     = info.get("title", title)
            thumbnail = info.get("thumbnail", thumbnail)
    except Exception as e:
        print(f"[Phase1] {e}")
    try:
        with yt_dlp.YoutubeDL(build_opts(url, fpath)) as ydl:
            ydl.download([url])
        sf = find_file(file_id)
        if not sf:
            raise FileNotFoundError("الملف لم يوجد.")
        return jsonify({
            "title":             title,
            "thumbnail":         thumbnail,
            "preview_type":      "video",
            "stream_url":        f"/stream/{sf}",
            "download_url_high": f"/stream/{sf}?dl=1",
            "download_url_low":  f"/stream/{sf}?dl=1",
        })
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "403"           in msg: err = "المنصة رفضت الطلب (403)."
        elif "Private"     in msg: err = "هذا المحتوى خاص."
        elif "unavailable" in msg.lower(): err = "المحتوى غير متاح."
        else: err = f"فشل التحميل: {msg[-120:]}"
        return jsonify({"error": err}), 500
    except Exception as e:
        return jsonify({"error": f"خطأ: {str(e)[-100:]}"}), 500

@app.route("/stream/<filename>")
def stream_video(filename):
    filename = os.path.basename(filename)
    path     = os.path.join(DOWNLOAD_FOLDER, filename)
    force_dl = request.args.get("dl") == "1"

    if not os.path.exists(path):
        abort(404)

    size = os.path.getsize(path)

    # تحميل مباشر
    if force_dl:
        return Response(
            _chunks(path), status=200, mimetype="video/mp4",
            headers={
                "Content-Length":      str(size),
                "Content-Disposition": 'attachment; filename="video.mp4"',
                "Cache-Control":       "no-cache",
            }
        )

    rng = request.headers.get("Range")

    # بث كامل
    if not rng:
        return Response(
            _chunks(path), status=200, mimetype="video/mp4",
            headers={
                "Content-Length": str(size),
                "Accept-Ranges":  "bytes",
                "Cache-Control":  "no-cache",
            }
        )

    # Partial Content
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
        _chunks(path, b1, ln), status=206, mimetype="video/mp4",
        headers={
            "Content-Range":  f"bytes {b1}-{b2}/{size}",
            "Accept-Ranges":  "bytes",
            "Content-Length": str(ln),
            "Cache-Control":  "no-cache",
        }
    )


def _chunks(path, start=0, length=None):
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
