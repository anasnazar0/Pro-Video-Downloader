import os, re, uuid, time, subprocess, sys
import urllib.parse
import requests
from flask import Flask, render_template, request, jsonify, Response, abort, redirect
import yt_dlp, imageio_ffmpeg

# ✅ تحديث yt-dlp التلقائي
try:
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "-q"],
                   check=True, timeout=60)
    print("[INFO] yt-dlp updated.")
except Exception as e:
    print(f"[WARN] {e}")

app = Flask(__name__)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# ✅ PHASE 1 OPTS: خيارات استخراج مرنة جداً (بدون تحديد Format لمنع انهيار يوتيوب)
EXTRACT_OPTS = {
    "quiet":              True,
    "no_warnings":        True,
    "nocheckcertificate": True,
    "extract_flat":       False,
}
if os.path.exists("cookies.txt"):
    EXTRACT_OPTS["cookiefile"] = "cookies.txt"


def get_best_direct_url(info):
    """جلب أفضل رابط مباشر مدمج"""
    formats = info.get("formats", [])
    for f in reversed(formats):
        if (f.get('vcodec') not in ('none', None)
                and f.get('acodec') not in ('none', None)
                and f.get('ext') == 'mp4'
                and f.get('url')):
            return f['url']
    for f in reversed(formats):
        if (f.get('vcodec') not in ('none', None)
                and f.get('acodec') not in ('none', None)
                and f.get('url')):
            return f['url']
    return info.get('url')


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

    url      = body["url"]
    file_id  = str(uuid.uuid4())
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    title     = "Video"
    thumbnail = "https://img.icons8.com/color/96/000000/video.png"
    dl_url    = None
    fb_url    = None

    # ══ PHASE 1: استخراج المعلومات بحرية تامة ══
    try:
        with yt_dlp.YoutubeDL(EXTRACT_OPTS) as ydl:
            info      = ydl.extract_info(url, download=False)
            title     = info.get("title", title)
            thumbnail = info.get("thumbnail", thumbnail)
            fb_url    = info.get("url")
            dl_url    = get_best_direct_url(info)
    except Exception as e:
        return jsonify({"error": f"فشل استخراج المعلومات: {e}"}), 500

    # ══ PHASE 2: تحميل للبث المباشر مع تطبيق صيغ الدمج ══
    stream_url   = ""
    preview_type = "video"

    try:
        opts = dict(EXTRACT_OPTS)
        opts.update({
            "ffmpeg_location":     FFMPEG_PATH,
            # تطبيق شروط الصيغ فقط أثناء التحميل لتجنب الأخطاء
            "format":              "bv*[height<=480]+ba/b[height<=480]/b/best",
            "outtmpl":             filepath,
            "merge_output_format": "mp4",
            "retries":             3,
            "fragment_retries":    3,
        })

        with yt_dlp.YoutubeDL(opts) as ydl:
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

    # تجهيز روابط الوكيل (Proxy)
    safe_title = urllib.parse.quote(title)
    proxy_high = f"/proxy?title={safe_title}&url={urllib.parse.quote(dl_url)}" if dl_url else None
    proxy_low  = f"/proxy?title={safe_title}&url={urllib.parse.quote(fb_url)}" if fb_url else None

    return jsonify({
        "title":             title,
        "thumbnail":         thumbnail,
        "stream_url":        stream_url,
        "preview_type":      preview_type,
        "download_url_high": proxy_high or dl_url,
        "download_url_low":  proxy_low or fb_url,
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
        return Response(_chunks(path), status=200, mimetype="video/mp4",
                        headers={"Content-Length": str(size),
                                 "Accept-Ranges":  "bytes",
                                 "Cache-Control":  "no-cache"})

    m = re.search(r"bytes=(\d+)-(\d*)", rng)
    if not m:
        abort(416)

    b1 = int(m.group(1))
    b2 = int(m.group(2)) if m.group(2) else size - 1
    b2 = min(b2, size - 1)
    if b1 > b2:
        abort(416)

    ln = b2 - b1 + 1
    return Response(_chunks(path, b1, ln), status=206, mimetype="video/mp4",
                    headers={"Content-Range":  f"bytes {b1}-{b2}/{size}",
                             "Accept-Ranges":  "bytes",
                             "Content-Length": str(ln),
                             "Cache-Control":  "no-cache"})


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


# ── 🚀 الوكيل السري (Proxy) المحدّث ──
@app.route("/proxy")
def proxy_download():
    target_url = request.args.get("url")
    title = request.args.get("title", "VidFetch_Video")
    
    if not target_url:
        abort(400)
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    try:
        r = requests.get(target_url, headers=headers, stream=True, timeout=10)
        r.raise_for_status() 
        
        def generate():
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    yield chunk
                    
        safe_title = urllib.parse.unquote(title) 
        encoded_title = urllib.parse.quote(safe_title)
        
        return Response(generate(), 
                        mimetype=r.headers.get('Content-Type', 'video/mp4'),
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_title}.mp4"})
    except Exception as e:
        print(f"[PROXY ERROR]: {e}")
        # ✅ الحل السحري: إذا فشل الوكيل، سيقوم بتوجيه المستخدم للرابط المباشر بدلاً من صفحة 500
        return redirect(target_url)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
