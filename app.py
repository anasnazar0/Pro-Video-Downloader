import os
import re
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ==========================================
# 🛡️ الطبقة الأمنية 1: التحقق من صحة الرابط
# ==========================================
def is_valid_url(url):
    """تتأكد أن المدخل هو رابط إنترنت حقيقي وليس كود اختراق"""
    regex = re.compile(
        r'^(?:http|ftp)s?://' # يجب أن يبدأ بـ http:// أو https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # النطاق
        r'localhost|' # أو لوكال هوست
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # أو عنوان IP
        r'(?::\d+)?' # المنفذ (اختياري)
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    body = request.get_json()
    
    # 1. التحقق من وجود بيانات
    if not body or not body.get("url"):
        return jsonify({"error": "الرجاء إرسال رابط صحيح."}), 400

    raw_url = body["url"].strip()

    # 2. الفحص الأمني للرابط
    if not is_valid_url(raw_url):
        return jsonify({"error": "⚠️ محاولة غير صالحة. الرجاء إدخال رابط إنترنت آمن."}), 400

    # ==========================================
    # 🚀 الطبقة 2: الاتصال الآمن بـ Cobalt API
    # ==========================================
    API_URL = "https://api.cobalt.tools/api/json"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        # تحديد هوية التطبيق لتجنب الحظر من الـ API
        "User-Agent": "VidFetch-Secure-Server/1.0" 
    }
    
    payload = {
        "url": raw_url,
        "videoQuality": "max", # طلب أعلى جودة دائماً
        "filenamePattern": "classic" # اسم ملف نظيف
    }

    try:
        # إرسال الطلب مع تحديد وقت أقصى (Timeout) لمنع تعليق السيرفر
        response = requests.post(API_URL, json=payload, headers=headers, timeout=15)
        
        # إذا كان السيرفر الخارجي معطلاً (مثل 500 أو 429)
        if response.status_code != 200:
            raise Exception("سيرفرات التحميل تواجه ضغطاً حالياً. يرجى المحاولة بعد قليل.")

        data = response.json()

        # إذا الـ API نفسه أرجع خطأ (مثلاً الرابط خاص أو غير مدعوم)
        if data.get("status") == "error":
            error_text = data.get("text", "الفيديو غير متاح أو محمي.")
            raise Exception(f"الخدمة: {error_text}")

        # استخراج الرابط النظيف من الـ API
        direct_url = data.get("url")

        # ==========================================
        # 🛡️ الطبقة الأمنية 3: تعقيم المخرجات
        # ==========================================
        if not direct_url or not direct_url.startswith("https://"):
            raise Exception("تم استلام استجابة غير آمنة من المزود. تم حجب العملية حمايةً لك.")

        # تجهيز البيانات للواجهة الأمامية (متوافقة 100% مع كود الـ HTML الخاص بك)
        return jsonify({
            "title": "VidFetch Video (Secure)", 
            "thumbnail": "https://img.icons8.com/color/96/000000/video.png",
            "stream_url": direct_url,
            "preview_type": "video",
            "download_url_high": direct_url,
            "download_url_low": direct_url,
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "⚠️ انتهى وقت الاتصال. السيرفرات مشغولة، حاول مجدداً."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
