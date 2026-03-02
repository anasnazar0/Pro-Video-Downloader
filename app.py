import os
import re
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# 🛡️ التحقق من صحة الرابط
def is_valid_url(url):
    regex = re.compile(
        r'^(?:http|ftp)s?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    body = request.get_json()
    if not body or not body.get("url"):
        return jsonify({"error": "الرجاء إرسال رابط صحيح."}), 400

    raw_url = body["url"].strip()
    if not is_valid_url(raw_url):
        return jsonify({"error": "⚠️ رابط غير صالح."}), 400

    # ==========================================
    # 🚀 شبكة خوادم Cobalt (نظام التوفر العالي Failover)
    # ==========================================
    COBALT_INSTANCES = [
        "https://api.cobalt.tools/",           # السيرفر الرسمي
        "https://cobalt-api.kwiatekmiki.com/", # سيرفر احتياطي 1
        "https://api.cobalt.lol/",             # سيرفر احتياطي 2
        "https://cobalt.qas.im/",              # سيرفر احتياطي 3
        "https://api.zeon.dev/"                # سيرفر احتياطي 4
    ]
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "url": raw_url
    }

    direct_url = None
    last_error = "جميع السيرفرات تواجه ضغطاً حالياً. يرجى المحاولة بعد قليل."

    # المرور على السيرفرات واحداً تلو الآخر حتى ينجح أحدهم
    for api_url in COBALT_INSTANCES:
        try:
            # مهلة 8 ثوانٍ لكل سيرفر لكي لا يطول الانتظار
            response = requests.post(api_url, json=payload, headers=headers, timeout=8)
            
            if response.status_code == 200:
                data = response.json()
                
                # إذا السيرفر أرجع خطأ داخلي (مثل فيديو خاص)
                if data.get("status") == "error":
                    last_error = data.get("text", "الفيديو غير متاح أو محمي.")
                    continue # السيرفر رد بخطأ، جرب السيرفر الذي يليه

                # إذا وجدنا الرابط بنجاح!
                if data.get("url"):
                    direct_url = data.get("url")
                    break # نجحنا! نوقف البحث فوراً
                    
        except Exception:
            # إذا كان السيرفر معطلاً تماماً، انتقل للذي بعده بصمت
            continue 

    # إذا فشلت كل السيرفرات الخمسة (احتمال شبه مستحيل)
    if not direct_url:
        return jsonify({"error": f"⚠️ {last_error}"}), 500

    # تجهيز البيانات للواجهة الأمامية
    return jsonify({
        "title": "VidFetch Video", 
        "thumbnail": "https://img.icons8.com/color/96/000000/video.png",
        "stream_url": direct_url,
        "download_url_high": direct_url,
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
