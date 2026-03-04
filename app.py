import os, re, uuid, time, subprocess, sys, json
import urllib.request
from flask import Flask, render_template, request, jsonify, send_file, abort
import yt_dlp, imageio_ffmpeg
import threading
import importlib

# ==========================================
# 1. نظام التحديث التلقائي
# ==========================================
def update_and_reload_ytdlp():
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "-q"],
                       capture_output=True, text=True, timeout=120)
        importlib.reload(yt_dlp)
    except Exception as e:
        pass

def background_updater():
    while True:
        time.sleep(43200) # كل 12 ساعة
        update_and_reload_ytdlp()

update_and_reload_ytdlp()
threading.Thread(target=background_updater, daemon=True).start()

# ==========================================
# 2. إعدادات السيرفر
# ==========================================
app = Flask(__name__)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
COOKIES = "cookies.txt" if os.path.exists("cookies.txt") else None
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# ==========================================
# 3. دوال المنصات والتنظيف
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
# 4. بناء الإعدادات (هنا تم حل مشكلة الدمج والعرض 🚀)
# ==========================================
def build_opts(url, filepath=None):
    opts = {
        "quiet":              True,
        "no_warnings":        True,
        "nocheckcertificate": True,
        "check_formats":      False,
        "http_headers": {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    if COOKIES:
        opts["cookiefile"] = COOKIES

    if is_youtube(url):
        opts["extractor_args"] = {"youtube": {"player_client": ["tv_embedded", "ios", "android", "mweb"]}}
        opts["geo_bypass"] = True
    elif is_tiktok(url):
        opts["http_headers"]["Referer"] = "https://www.tiktok.com/"
    elif is_instagram(url):
        opts["http_headers"]["Referer"] = "https://www.instagram.com/"

    if filepath:
        # ✅ 1. إجبار الأداة على سحب صيغ متوافقة مع الويب لضمان نجاح الدمج
        fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        
        opts.update({
            "ffmpeg_location":     FFMPEG_PATH,
            "format":              fmt,
            "outtmpl":             filepath,
            "merge_output_format": "mp4",
            
            # ✅ 2. السر السحري: نقل بيانات الـ MOOV للبداية ليعمل الفيديو فوراً في المتصفح
            "postprocessor_args": [
                '-movflags', '+faststart'
            ],
            
            "retries":             3,
            "fragment_retries":    3,
        })

    return opts

# ==========================================
# 5. مسارات الواجهة والتحميل
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
        with yt_dlp.YoutubeDL(build_opts(url)) as ydl:
            info      = ydl.extract_info(url, download=False)
            title     = info.get("title", title)
            thumbnail = info.get("thumbnail", thumbnail)
    except Exception as e:
        print(f"[Extraction Error] {e}")
        
    try:
        # التحميل والدمج مع faststart
        with yt_dlp.YoutubeDL(build_opts(url, fpath)) as ydl:
            ydl.download([url])
            
        sf = find_file(file_id)
        if not sf:
            raise FileNotFoundError("تعذر العثور على الملف.")
            
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
        if "403" in msg: err = "المنصة رفضت الطلب (403 Forbidden)."
        elif "Private" in msg: err = "هذا المحتوى خاص."
        else: err = "فشل التحميل، الرابط غير مدعوم أو محمي."
        return jsonify({"error": err}), 500
    except Exception as e:
        return jsonify({"error": "حدث خطأ داخلي في السيرفر أثناء المعالجة."}), 500


# ==========================================
# 6. نظام البث الاحترافي (Streaming)
# ==========================================
@app.route("/stream/<filename>")
def stream_video(filename):
    """نظام بث متقدم باستخدام أدوات Flask المدمجة لدعم التقديم والتأخير"""
    filename = os.path.basename(filename)
    path     = os.path.join(DOWNLOAD_FOLDER, filename)
    force_dl = request.args.get("dl") == "1"

    if not os.path.exists(path):
        abort(404)

    # ✅ استخدام send_file مع conditional=True يحل جميع مشاكل مشغل الفيديو في المتصفحات
    return send_file(
        path,
        as_attachment=force_dl,
        download_name="VidFetch_Video.mp4" if force_dl else None,
        mimetype="video/mp4",
        conditional=True # هذا يفعل دعم الـ 206 Partial Content أوتوماتيكياً
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)
