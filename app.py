import os
import uuid
import requests
import re
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
import yt_dlp

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] += os.pathsep + CURRENT_DIR

app = Flask(__name__)

if not os.path.exists('downloads'):
    os.makedirs('downloads')

YDL_BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'cookiefile': 'cookies.txt', 
}

# دالة صغيرة لاستخراج كود يوتيوب لتشغيل المشغل
def get_yt_id(url):
    match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11}).*', url)
    return match.group(1) if match else None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    data = request.get_json()
    url = data.get('url')

    if not url:
        return jsonify({'error': 'Please provide a valid URL'}), 400

    # 🧠 العقل الأول: يوتيوب (جلب رابط التحميل + رابط المشغل)
    if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
        try:
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0'
            }
            payload = {'url': url}
            response = requests.post('https://api.cobalt.tools/api/json', json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                res_data = response.json()
                if res_data.get('url'):
                    yt_id = get_yt_id(url)
                    # صنع رابط المشغل الرسمي ليوتيوب
                    preview_url = f"https://www.youtube.com/embed/{yt_id}" if yt_id else None
                    
                    return jsonify({
                        'title': 'YouTube Video',
                        'thumbnail': 'https://img.icons8.com/color/96/000000/youtube-play.png', 
                        'preview_url': preview_url,
                        'preview_type': 'iframe' if preview_url else 'image',
                        'formats': [{
                            'id': 'best',
                            'resolution': 'تحميل يوتيوب المباشر (سريع جداً)',
                            'ext': 'mp4',
                            'url': res_data.get('url')
                        }]
                    })
        except:
            pass 

    # 🧠 العقل الثاني: باقي المنصات (تيك توك، انستا، الخ)
    try:
        with yt_dlp.YoutubeDL(YDL_BASE_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            
            preview_url = None
            preview_type = 'video'
            
            # صنع مشغل تيك توك الرسمي
            if 'tiktok.com' in url.lower():
                video_id = info.get('id')
                preview_url = f"https://www.tiktok.com/embed/v2/{video_id}"
                preview_type = 'iframe'
            else:
                preview_url = info.get('url') # مشغل فيديو عادي للبقية

            formats = [{
                'id': 'best',
                'resolution': 'تحميل أفضل جودة (MP4)',
                'ext': 'mp4',
                'url': f'/download_video?url={url}'
            }]

            return jsonify({
                'title': info.get('title', 'Video Downloader'),
                'thumbnail': info.get('thumbnail', ''),
                'preview_url': preview_url,
                'preview_type': preview_type,
                'formats': formats
            })
    except Exception as e:
        return jsonify({'error': f"يوتيوب أو المنصة ترفض الرابط مؤقتاً. حاول لاحقاً."}), 500

@app.route('/download_video')
def download_video():
    url = request.args.get('url')
    file_id = str(uuid.uuid4())
    filepath = os.path.join('downloads', f"{file_id}.%(ext)s")
    
    dl_opts = dict(YDL_BASE_OPTS)
    dl_opts.update({
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': filepath,
        'merge_output_format': 'mp4',
    })
    
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([url])
        
        final_filepath = None
        for file in os.listdir('downloads'):
            if file.startswith(file_id):
                final_filepath = os.path.join('downloads', file)
                break
                
        if not final_filepath:
            return "Download failed.", 500
        
        @after_this_request
        def remove_file(response):
            try:
                if os.path.exists(final_filepath):
                    os.remove(final_filepath)
            except:
                pass
            return response

        return send_file(final_filepath, as_attachment=True, download_name="Video_Pro.mp4")
        
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
