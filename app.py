import os
import re
import uuid
import time
import subprocess
import sys
import json
import threading
import importlib
import urllib.request
from flask import Flask, render_template, request, jsonify, Response, abort
import yt_dlp
import imageio_ffmpeg

# ==========================================
# 1. نظام التحديث التلقائي الذكي (الخلفية)
# ==========================================
def update_and_reload_ytdlp():
    """دالة تقوم بتحديث المكتبة وإعادة تحميلها في الذاكرة الحية"""
    try:
        print("[AUTO-UPDATE] Checking for yt-dlp updates...")
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "-q"],
                                capture_output=True, text=True, timeout=120)
        
        # إجبار بايثون على استخدام النسخة الجديدة فوراً دون إطفاء السيرفر
        importlib.reload(yt_dlp)
        print("[AUTO-UPDATE] yt-dlp updated and reloaded successfully in memory.")
    except Exception as e:
        print(f"[AUTO-UPDATE ERROR] Failed to update: {e}")

def background_updater():
    """خيط برمجي (Thread) يعمل في الخلفية ويستيقظ كل 12 ساعة"""
    while True:
        # الانتظار لمدة 12 ساعة (43200 ثانية)
        time.sleep(43200)
        update_and_reload_ytdlp()

# تشغيل التحديث مرة واحدة عند إقلاع السيرفر
update_and_reload_ytdlp()

# تشغيل المراقب الخفي في الخلفية (daemon=True تعني أنه لن يعيق إطفاء السيرفر)
updater_thread = threading.Thread(target=background_updater, daemon=True)
updater_thread.start()


# ==========================================
# 2. إعدادات السيرفر الأساسية
# ==========================================
app = Flask(__name__)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
COOKIES = "cookies.txt" if os.path.exists("cookies.txt") else None
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ==========================================
# 3. دوال كشف المنصات وتنظيف الملفات
# ==========================================
def is_youtube(url):   return "youtube.com" in url or "youtu.be" in url
def is_tiktok(url):    return "tiktok.com" in url
def is_instagram(url): return "instagram.com" in url

def extract_yt_id(url):
    m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None

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
                os.remove(p)
    except Exception:
        pass


# ==========================================
# 4. بناء الإعدادات لأعلى جودة (بلا حدود)
# ==========================================
def build_opts(url, filepath=None):
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

    if filepath:
        fmt = (
            "bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/"
            "best"
        )
        opts.update({
            "ffmpeg_location":     FFMPEG_PATH,
            "format":              fmt,
            "outtmpl":             filepath,
            "merge_output_format": "mp4",
            "postprocessors": [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            "retries":             5,
            "fragment_retries":    5,
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
        
    url = body["url"].strip()

    file_id = str(uuid.uuid4())
    fpath   = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")
    
    title     = "VidFetch Video"
    thumbnail = "https://img.icons8.com/color/96/000000/video.png"
    
    try:
        # المرحلة الأولى: استخراج البيانات الوصفية فقط
        with yt_dlp.YoutubeDL(build_opts(url)) as ydl:
            info      = ydl.extract_info(url, download=False)
            title     = info.get("title", title)
            thumbnail = info.get("thumbnail", thumbnail)
    except Exception as e:
        print(f"[Extraction Error] {e}")
        
    try:
        # المرحلة الثانية: التحميل والدمج بأعلى جودة
        with yt_dlp.YoutubeDL(build_opts(url, fpath)) as ydl:
            ydl.download([url])
            
        sf = find_file(file_id)
        if not sf:
            raise FileNotFoundError("تعذر العثور على الملف بعد التحميل.")
            
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
        if "403" in msg: 
            err = "المنصة رفضت الطلب (403 Forbidden)."
        elif "Private" in msg: 
            err = "هذا المحتوى خاص ولا يمكن الوصول إليه."
        elif "unavailable" in msg.lower(): 
            err = "المحتوى غير متاح أو تم حذفه."
        else: 
            err = "فشل التحميل، تأكد من صحة الرابط."
        return jsonify({"error": err}), 500
    except Exception as e:
        print(f"[Internal Error] {e}")
        return jsonify({"error": "حدث خطأ داخلي في السيرفر أثناء المعالجة."}), 500


@app.route("/stream/<filename>")
def stream_video(filename):
    filename = os.path.basename(filename)
    path     = os.path.join(DOWNLOAD_FOLDER, filename)
    force_dl = request.args.get("dl") == "1"

    if not os.path.exists(path):
        abort(404)

    size = os.path.getsize(path)

    if force_dl:
        return Response(
            _chunks(path), status=200, mimetype="video/mp4",
            headers={
                "Content-Length":      str(size),
                "Content-Disposition": 'attachment; filename="VidFetch_Video.mp4"',
                "Cache-Control":       "no-cache",
            }
        )

    rng = request.headers.get("Range")

    if not rng:
        return Response(
            _chunks(path), status=200, mimetype="video/mp4",
            headers={
                "Content-Length": str(size),
                "Accept-Ranges":  "bytes",
                "Cache-Control":  "no-cache",
            }
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
