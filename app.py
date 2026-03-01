import os
import uuid
import time
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# إعدادات التحميل لضمان العمل على كل الأجهزة
YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "cookiefile": "cookies.txt", # لا تنسى إبقاء ملف الكوكيز لتخطي حظر يوتيوب
}

# دالة التنظيف التلقائي: تمسح الفيديوهات التي مر عليها أكثر من 30 دقيقة
def cleanup_old_files():
    try:
        current_time = time.time()
        for filename in os.listdir(DOWNLOAD_FOLDER):
            filepath = os.path.join(DOWNLOAD_FOLDER, filename)
            # مسح الملفات الأقدم من 1800 ثانية (30 دقيقة)
            if os.path.isfile(filepath) and (current_time - os.path.getmtime(filepath) > 1800):
                os.remove(filepath)
    except Exception as e:
        pass

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    # تشغيل التنظيف التلقائي في كل مرة يطلب فيها شخص فيديو جديد
    cleanup_old_files()
    
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "الرابط غير صالح"}), 400

    file_id = str(uuid.uuid4())
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.%(ext)s")

    opts = dict(YDL_OPTS)
    opts.update({
        "format": "bestvideo[vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": filepath,
        "merge_output_format": "mp4",
    })

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # استخراج العنوان والصورة المصغرة قبل التحميل
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Video')
            thumbnail = info.get('thumbnail', 'https://img.icons8.com/color/96/000000/video.png')
            
            # التحميل الفعلي للسيرفر
            ydl.download([url])

        final_file = None
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(file_id):
                final_file = f
                break

        if not final_file:
            return jsonify({"error": "فشل تحميل الفيديو."}), 500

        # إرجاع روابط البث والتحميل الخاصة بسيرفرك للواجهة
        return jsonify({
            "title": title,
            "thumbnail": thumbnail,
            "stream_url": f"/stream/{final_file}",
            "download_url": f"/file/{final_file}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stream/<filename>")
def stream_video(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)

    if not os.path.exists(filepath):
        return "الملف غير موجود أو انتهت صلاحيته", 404

    # السحر هنا: conditional=True تقوم بعمل Stream احترافي يدعم التقديم والتأخير بدون استهلاك للرام!
    return send_file(filepath, mimetype="video/mp4", conditional=True)

@app.route("/file/<filename>")
def download_file(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)

    if not os.path.exists(filepath):
        return "الملف غير موجود أو انتهت صلاحيته", 404

    return send_file(filepath, as_attachment=True, download_name="Universal_Video.mp4")

if __name__ == "__main__":
    app.run(debug=True)
