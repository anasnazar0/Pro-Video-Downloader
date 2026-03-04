import os
import re
import uuid
import time
import subprocess
import sys
import threading
import mimetypes
import shutil
import importlib
from flask import Flask, render_template, request, jsonify, Response, send_file, abort
import yt_dlp
import imageio_ffmpeg

# ==========================================
# 1. نظام التحديث التلقائي (الخلفية)
# ==========================================
def update_ytdlp():
    """تحديث yt-dlp وإعادة تحميلها في الذاكرة الحية"""
    try:
        print("[AUTO-UPDATE] Checking for yt-dlp updates...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "-q"],
            capture_output=True, text=True, timeout=120
        )
        importlib.reload(yt_dlp)
        print("[AUTO-UPDATE] yt-dlp updated and reloaded.")
    except Exception as e:
        print(f"[AUTO-UPDATE ERROR] {e}")

def background_updater():
    """خيط خلفي يتحقق من التحديثات كل 12 ساعة"""
    while True:
        time.sleep(43200)
        update_ytdlp()

update_ytdlp()
threading.Thread(target=background_updater, daemon=True).start()

# ==========================================
# 2. إعدادات السيرفر الأساسية
# ==========================================
app = Flask(__name__)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
COOKIES = "cookies.txt" if os.path.exists("cookies.txt") else None
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

URL_PATTERN = re.compile(
    r'^https?://'
    r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+'
    r'[A-Za-z]{2,}'
    r'(?:/[^\s]*)?$'
)

# ==========================================
# 3. دوال مساعدة
# ==========================================
def is_youtube(url):   return "youtube.com" in url or "youtu.be" in url
def is_tiktok(url):    return "tiktok.com" in url
def is_instagram(url): return "instagram.com" in url

def extract_yt_id(url):
    m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None

def validate_url(url):
    url = url.strip()
    return url if URL_PATTERN.match(url) else None

def get_mime(filename):
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"

def check_disk_space(min_mb=100):
    try:
        usage = shutil.disk_usage(DOWNLOAD_FOLDER)
        return (usage.free / (1024 * 1024)) >= min_mb
    except Exception:
        return True

def find_file(file_id):
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
                try: os.remove(p)
                except OSError: pass
    except Exception as e:
        print(f"[CLEANUP ERROR] {e}")

# ==========================================
# 4. بناء إعدادات yt-dlp
# ==========================================
def build_opts(url, filepath=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "http_headers": {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
    }

    if COOKIES: opts["cookiefile"] = COOKIES

    if is_youtube(url):
        opts["extractor_args"] = {"youtube": {"player_client": ["tv_embedded", "ios", "android", "mweb"]}}
        opts["geo_bypass"] = True
    elif is_tiktok(url):
        opts["http_headers"]["Referer"] = "https://www.tiktok.com/"
    elif is_instagram(url):
        opts["http_headers"]["Referer"] = "https://www.instagram.com/"

    if filepath:
        fmt = (
            "bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/best"
        )
        opts.update({
            "ffmpeg_location": FFMPEG_PATH,
            "format": fmt,
            "outtmpl": filepath,
            "merge_output_format": "mp4",
            "postprocessors": [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
            # الصيغة الصحيحة لتمرير faststart لضمان العرض المباشر في المتصفح
            "postprocessor_args": {'ffmpeg': ['-movflags', '+faststart']},
            "retries": 5,
            "fragment_retries": 5,
        })
    return opts

# ==========================================
# 5. مسارات الواجهة والتحميل (Routes)
# ==========================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    cleanup_old_files()

    body = request.get_json()
    if not body or not body.get("url"):
        return jsonify({"error": "الرجاء إرسال رابط صحيح."}), 400

    url = validate_url(body["url"])
    if not url:
        return jsonify({"error": "الرابط غير صحيح. يجب أن يبدأ بـ http:// أو https://"}), 400

    if not check_disk_space():
        cleanup_old_files()
        if not check_disk_space():
            return jsonify({"error": "مساحة السيرفر ممتلئة. حاول لاحقاً."}), 507

    file_id = str(uuid.uuid4())
    fpath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    try:
        with yt_dlp.YoutubeDL(build_opts(url, fpath)) as ydl:
            info = ydl.extract_info(url, download=True)

        title = info.get("title", "VidFetch Video")
        thumbnail = info.get("thumbnail", "https://img.icons8.com/color/96/000000/video.png")

        if is_youtube(url):
            yt_id = extract_yt_id(url)
            if yt_id: thumbnail = f"https://i.ytimg.com/vi/{yt_id}/maxresdefault.jpg"

        sf = find_file(file_id)
        if not sf: raise FileNotFoundError()

        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "preview_type": "video",
            "stream_url": f"/stream/{sf}",
            "download_url_high": f"/stream/{sf}?dl=1",
        })

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "403" in msg: return jsonify({"error": "المنصة رفضت الطلب (403)."}), 403
        elif "Private" in msg: return jsonify({"error": "هذا المحتوى خاص."}), 403
        elif "unavailable" in msg.lower(): return jsonify({"error": "المحتوى غير متاح."}), 404
        else: return jsonify({"error": "فشل التحميل، تأكد من الرابط."}), 500
    except Exception as e:
        print(f"[Internal Error] {e}")
        return jsonify({"error": "حدث خطأ داخلي في السيرفر."}), 500

@app.route("/stream/<filename>")
def stream_video(filename):
    filename = os.path.basename(filename)
    path = os.path.join(DOWNLOAD_FOLDER, filename)

    if not os.path.exists(path): abort(404)

    force_dl = request.args.get("dl") == "1"
    mime = get_mime(filename)

    # استخدام send_file المدمج لدعم 206 Partial Content تلقائياً
    return send_file(
        path,
        mimetype=mime,
        as_attachment=force_dl,
        download_name="VidFetch_Video.mp4" if force_dl else None,
        conditional=True
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"

    if debug:
        app.run(debug=True, port=port)
    else:
        from waitress import serve
        print(f"[VidFetch] Production server running on port {port}")
        serve(app, host="0.0.0.0", port=port, threads=4)