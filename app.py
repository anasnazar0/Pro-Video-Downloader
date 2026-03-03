import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    body = request.get_json()
    
    # يجب أن نستلم الرابط، واسم السيرفر من الواجهة الأمامية
    if not body or not body.get("url") or not body.get("api_url"):
        return jsonify({"error": "بيانات مفقودة."}), 400

    raw_url = body["url"].strip()
    api_url = body["api_url"].strip()

    # استخراج الـ IP الحقيقي وتمريره للمجتمع
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

    try:
        # الاتصال بالسيرفر الذي طلبته الواجهة الأمامية
        # حددنا 7 ثوان كحد أقصى لكي لا يطول انتظار المستخدم
        response = requests.post(api_url, json=payload, headers=headers, timeout=7)
        
        if response.status_code != 200:
            return jsonify({"error": "السيرفر مشغول."}), 500

        data = response.json()

        # إذا رد السيرفر بخطأ (مثلا الفيديو خاص أو محذوف)
        if data.get("status") == "error":
            error_msg = data.get("text", "الفيديو غير متاح.")
            # إرسال is_fatal لإخبار الواجهة بأن لا تتعب نفسها بتجربة باقي السيرفرات
            is_fatal = "supported" in error_msg.lower() or "private" in error_msg.lower()
            return jsonify({"error": error_msg, "is_fatal": is_fatal}), 400

        direct_url = data.get("url")

        if not direct_url:
            return jsonify({"error": "تعذر جلب الرابط."}), 500

        return jsonify({
            "title": "VidFetch Video", 
            "thumbnail": "https://img.icons8.com/color/96/000000/video.png",
            "stream_url": direct_url,
            "download_url_high": direct_url,
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "انتهى وقت الاتصال بالسيرفر."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
