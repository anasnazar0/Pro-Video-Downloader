import os
import random
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ==========================================
# 🌐 شبكة سيرفرات Cobalt (المجتمعية + الرسمي)
# ==========================================
COBALT_INSTANCES = [
    "https://co.wuk.sh/api/json",                     # سيرفر مجتمعي قوي جداً
    "https://cobalt-api.kwiatekmiki.com/api/json",    # سيرفر مجتمعي سريع
    "https://api.cobalt.lol/api/json",                # سيرفر مجتمعي 3
    "https://cobalt.qas.im/api/json",                 # سيرفر مجتمعي 4
    "https://api.zeon.dev/api/json",                  # سيرفر مجتمعي 5
    "https://api.cobalt.bepvte.website/api/json",     # سيرفر مجتمعي 6
    "https://api.cobalt.tools/api/json"               # السيرفر الرسمي (نجعله كاحتياط أخير)
]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    body = request.get_json()
    
    if not body or not body.get("url"):
        return jsonify({"error": "الرجاء إرسال رابط صحيح."}), 400

    raw_url = body["url"].strip()

    # 🧠 استخراج IP المستخدم الحقيقي وتمريره
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if user_ip and ',' in user_ip:
        user_ip = user_ip.split(',')[0].strip()

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://cobalt.tools/",
        "X-Forwarded-For": user_ip,
        "X-Real-IP": user_ip,
        "Client-IP": user_ip
    }
    
    payload = {
        "url": raw_url,
        "videoQuality": "max",
        "vCodec": "h264",
        "alwaysProxy": True,
        "filenamePattern": "classic"
    }

    # 🔄 خلط السيرفرات عشوائياً لتوزيع الضغط (Load Balancing)
    random.shuffle(COBALT_INSTANCES)

    direct_url = None
    last_error = "جميع السيرفرات تواجه ضغطاً حالياً. جرب بعد قليل."

    # 🚀 المرور على السيرفرات واحداً تلو الآخر حتى ينجح أحدها
    for api_url in COBALT_INSTANCES:
        try:
            # مهلة 7 ثوانٍ لكل سيرفر حتى لا ننتظر طويلاً إذا كان معطلاً
            response = requests.post(api_url, json=payload, headers=headers, timeout=7)
            
            if response.status_code == 200:
                data = response.json()
                
                # إذا رد السيرفر بخطأ في الفيديو نفسه
                if data.get("status") == "error":
                    last_error = data.get("text", "الفيديو غير متاح أو محمي.")
                    # إذا كان الرابط غير مدعوم إطلاقاً أو خاص، لا داعي لتجربة باقي السيرفرات
                    if "supported" in last_error.lower() or "private" in last_error.lower():
                        break
                    continue # جرب السيرفر التالي
                
                # إذا نجح السيرفر في جلب الرابط المباشر
                if data.get("url"):
                    direct_url = data.get("url")
                    break # 🛑 نجحنا! أوقف حلقة البحث فوراً

        except Exception as e:
            # إذا كان السيرفر محظوراً لـ Render أو لا يعمل، تجاوزه بصمت
            continue 

    # إذا فشلت كل السيرفرات الـ 7
    if not direct_url:
        return jsonify({"error": f"⚠️ {last_error}"}), 500

    return jsonify({
        "title": "VidFetch Video", 
        "thumbnail": "https://img.icons8.com/color/96/000000/video.png",
        "stream_url": direct_url,
        "download_url_high": direct_url,
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
