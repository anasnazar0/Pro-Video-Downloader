import os
from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    data = request.get_json()
    url = data.get('url')

    if not url:
        return jsonify({'error': 'Please provide a valid URL'}), 400

    try:
        # إرسال الرابط إلى سيرفرات Cobalt العملاقة لتخطي حماية يوتيوب
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        }
        payload = {
            'url': url,
            'vQuality': '720',
            'filenamePattern': 'classic'
        }
        
        # الاتصال بالـ API الخارجي
        response = requests.post('https://api.cobalt.tools/api/json', json=payload, headers=headers)
        result = response.json()
        
        # إذا رفض السيرفر الخارجي الرابط
        if response.status_code != 200 or result.get('status') == 'error':
            return jsonify({'error': 'عذراً، الرابط غير مدعوم أو السيرفر الخارجي مزدحم. جرب رابطاً آخر.'}), 400
            
        download_url = result.get('url')
        
        if not download_url:
            return jsonify({'error': 'فشل استخراج الرابط المباشر.'}), 400

        # إرسال الرابط المباشر للواجهة
        return jsonify({
            'title': 'جاهز للتحميل!',
            'thumbnail': 'https://img.icons8.com/color/96/000000/video.png', 
            'preview_url': None, 
            'preview_type': 'video',
            'formats': [{
                'id': 'best',
                'resolution': 'اضغط هنا لتحميل الفيديو (MP4)',
                'ext': 'mp4',
                'url': download_url # هذا الرابط سيحمل الفيديو للمستخدم مباشرة دون المرور بسيرفرك!
            }]
        })

    except Exception as e:
        return jsonify({'error': f"حدث خطأ في الاتصال: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
