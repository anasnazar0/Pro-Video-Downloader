import os
import uuid
import time
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# الإعدادات العامة
YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "cookiefile": "cookies.txt", 
}

# دالة تنظيف السيرفر لحمايته من الامتلاء (تحذف ما مر عليه 30 دقيقة)
def cleanup_old_files():
    try:
        current_time = time.time()
        for filename in os.listdir(DOWNLOAD_FOLDER):
            filepath = os.path.join(DOWNLOAD_FOLDER, filename)
            if os.path.isfile(filepath) and (current_time - os.path.getmtime(filepath) > 1800):
                os.remove(filepath)
    except Exception as e:
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
        return jsonify({"error": "الرابط غير صالح"}), 400

    file_id = str(uuid.uuid4())
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    try:
        # 1. المرحلة الأولى: استخراج الرابط المباشر بأعلى جودة للتحميل
        best_download_url = None
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl_info:
            info = ydl_info.extract_info(url, download=False)
            title = info.get('title', 'Video Ready')
            thumbnail = info.get('thumbnail', 'https://img.icons8.com/color/96/000000/video.png')
            
            # البحث عن أعلى جودة مدمجة (MP4) للتحميل المباشر
            formats = info.get('formats', [])
            for f in reversed(formats):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                    best_download_url = f.get('url')
                    break
            
            # إذا لم يجد صيغة مدمجة، نأخذ الرابط الافتراضي
            if not best_download_url:
                best_download_url = info.get('url')

        # 2. المرحلة الثانية: تحميل نسخة خفيفة (480p) للسيرفر من أجل البث
        stream_opts = dict(YDL_OPTS)
        stream_opts.update({
            # The Magic String Breakdown:
            # 1. bv*[height<=480]+ba : Best video (with or without audio) up to 480p + Best audio.
            # 2. b[height<=480]      : Fallback to Best pre-merged file up to 480p.
            # 3. bv*+ba              : Fallback to Best video + Best audio (ignore 480p limit if not found).
            # 4. b                   : Ultimate fallback to Best pre-merged file (ignore 480p limit).
            
            "format": "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b",
            "outtmpl": filepath,
            
            # Ensures the final output to the browser is always a playable MP4
            "merge_output_format": "mp4",
        })

        with yt_dlp.YoutubeDL(stream_opts) as ydl_down:
            ydl_down.download([url])

        final_file = None
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(file_id):
                final_file = f
                break

        if not final_file:
            return jsonify({"error": "فشل تجهيز الفيديو للبث."}), 500

        # إرجاع الروابط (رابط البث، رابط التحميل العالي، ورابط التحميل الاحتياطي)
        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "stream_url": f"/stream/{final_file}",
            "download_url_high": best_download_url if best_download_url else f"/file/{final_file}",
            "download_url_low": f"/file/{final_file}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stream/<filename>")
def stream_video(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return "الملف غير موجود أو انتهت صلاحيته", 404
    # البث الذكي المتقطع لإنقاذ الرام
    return send_file(filepath, mimetype="video/mp4", conditional=True)

@app.route("/file/<filename>")
def download_file(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return "الملف غير موجود أو انتهت صلاحيته", 404
    return send_file(filepath, as_attachment=True, download_name="Universal_Video.mp4")

if __name__ == "__main__":
    app.run(debug=True, port=5000)


