import os
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    body = request.get_json()
    
    if not body or not body.get("url"):
        return jsonify({"error": "الرجاء إرسال رابط صحيح."}), 400

    raw_url = body["url"].strip()

    # ==========================================
    # 🛡️ الاستراتيجية 3: التخفي كمتصفح حقيقي (Proper Headers)
    # ==========================================
    API_URL = "https://api.cobalt.tools/api/json"
    
    # 1. هذه الترويسات (Headers) هي السر.. تخبر السيرفر أننا حاسوب حقيقي ولسنا بوتاً
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Referer": "https://cobalt.tools/"
    }
    
    # 2. خيارات Cobalt المتقدمة (للحصول على فيديو مدمج بصوت وصورة)
    payload = {
        "url": raw_url,
        "videoQuality": "max",        # طلب أعلى جودة متوفرة (1080p فما فوق)
        "vCodec": "h264",             # صيغة مدعومة على الآيفون والأندرويد القديم والحديث
        "alwaysProxy": True,          # 🚀 السر لعدم ظهور خطأ 403 (إجبار التحميل عبر سيرفراتهم)
        "isAudioOnly": False,         # نريد فيديو وليس صوت فقط
        "filenamePattern": "classic"  # اسم ملف نظيف ومرتب
    }

    try:
        # إرسال الطلب للسيرفر مع هويتنا المزيفة
        response = requests.post(API_URL, json=payload, headers=headers, timeout=15)
        
        # إذا كشفنا السيرفر أو كان عليه ضغط
        if response.status_code != 200:
            raise Exception("سيرفرات التحميل تواجه ضغطاً أو ترفض الاتصال حالياً. حاول لاحقاً.")

        data = response.json()

        # إذا رد الـ API نفسه بوجود مشكلة في الفيديو (مثلا محذوف)
        if data.get("status") == "error":
            error_text = data.get("text", "الفيديو غير متاح أو محمي.")
            raise Exception(f"خطأ من المزود: {error_text}")

        # استخراج الرابط المباشر
        direct_url = data.get("url")

        if not direct_url:
            raise Exception("تمت المعالجة ولكن تعذر جلب رابط التحميل.")

        # إرسال البيانات الجاهزة لواجهة الموقع
        return jsonify({
            "title": "VidFetch Video", 
            "thumbnail": "https://img.icons8.com/color/96/000000/video.png",
            "stream_url": direct_url,
            "download_url_high": direct_url,
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "⚠️ انتهى وقت الاتصال. السيرفرات مشغولة جداً."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
