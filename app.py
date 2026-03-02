import os
import re
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ==========================================
# 🔑 إعدادات السيرفر التجاري (RapidAPI)
# ==========================================
# ⚠️ ضع مفتاحك السري هنا بين علامتي التنصيص
RAPIDAPI_KEY = "d125b5130fmsha9cd16bd72f1fc4p1b1ccejsnde077a9fb92f" 
RAPIDAPI_HOST = "social-media-video-downloader.p.rapidapi.com"
API_URL = "https://social-media-video-downloader.p.rapidapi.com/youtube/video_details"


def get_yt_video_id(url):
    """دالة لاستخراج المعرف (ID) من أي رابط يوتيوب"""
    regex = r'(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=|shorts\/))([\w-]{11})'
    match = re.search(regex, url)
    return match.group(1) if match else None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/download", methods=["POST"])
def download():
    body = request.get_json()
    
    if not body or not body.get("url"):
        return jsonify({"error": "الرجاء إرسال رابط صحيح."}), 400

    raw_url = body["url"].strip()
    video_id = get_yt_video_id(raw_url)
    
    if not video_id:
        return jsonify({"error": "⚠️ عذراً، هذا لا يبدو كرابط يوتيوب صالح."}), 400

    # إعدادات الطلب للـ API
    querystring = {
        "videoId": video_id,
        "renderableFormats": "720p,highres",
        "urlAccess": "proxied" # بروكسي لتخطي الحظر
    }

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        # إرسال الطلب
        response = requests.get(API_URL, headers=headers, params=querystring, timeout=15)
        
        if response.status_code != 200:
            return jsonify({"error": f"خطأ من مزود الخدمة: {response.status_code}"}), 500

        data = response.json()

        # ==========================================
        # 🔍 قراءة الـ JSON واستخراج الرابط
        # ==========================================
        contents = data.get("contents", [])
        if not contents:
            raise Exception("لم يتم العثور على محتوى للفيديو.")
            
        videos = contents[0].get("videos", [])
        direct_url = None
        
        # البحث عن أفضل جودة بصيغة mp4
        for vid in videos:
            mime = vid.get("metadata", {}).get("mime_type", "")
            if "mp4" in mime:
                direct_url = vid.get("url")
                break # نأخذ أول وأعلى جودة نجدها
                
        # إذا لم يجد mp4 تحديداً، يأخذ أي فيديو متوفر
        if not direct_url and videos:
            direct_url = videos[0].get("url")

        if not direct_url:
            raise Exception("تعذر جلب الرابط المباشر من مزود الخدمة.")

        # استخراج صورة مصغرة أنيقة
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

        return jsonify({
            "title": "VidFetch Premium Video", 
            "thumbnail": thumbnail_url,
            "stream_url": direct_url,
            "download_url_high": direct_url,
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "⚠️ انتهى وقت الاتصال بمزود الخدمة."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)

