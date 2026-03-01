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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    data = request.get_json()
    url = data.get('url')

    if not url:
        return jsonify({'error': 'Please provide a valid URL'}), 400

    # 🔴 يوتيوب: جلب الرابط المباشر للتشغيل والتحميل
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
                direct_url = res_data.get('url')
                if direct_url:
                    match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11}).*', url)
                    yt_id = match.group(1) if match else None
                    thumbnail = f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg" if yt_id else "https://img.icons8.com/color/96/000000/youtube-play.png"
                    
                    return jsonify({
                        'title': 'YouTube Video',
                        'thumbnail': thumbnail,
                        'preview_url': direct_url, # رابط مباشر للتشغيل في مشغل الموقع
                        'preview_type': 'video',
                        'formats': [{
                            'id': 'best',
                            'resolution': '⬇️ تحميل مباشر وسريع (MP4)',
                            'ext': 'mp4',
                            'url': direct_url
                        }]
                    })
        except:
            pass 

    # 🔵 باقي المنصات (تيك توك، انستا وغيرها)
    try:
        with yt_dlp.YoutubeDL(YDL_BASE_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # محاولة جلب رابط صالح للتشغيل المباشر داخل المتصفح
            preview_url = info.get('url')
            formats_list = info.get('formats', [])
            for f in formats_list:
                # نبحث عن صيغة عادية للتشغيل المسبق
                if f.get('vcodec') and 'avc' in f.get('vcodec').lower() and f.get('ext') == 'mp4' and f.get('acodec') != 'none':
                    preview_url = f.get('url')
                    break

            formats = [{
                'id': 'best',
                'resolution': '⬇️ تحميل أفضل جودة (MP4)',
                'ext': 'mp4',
                'url': f'/download_video?url={url}'
            }]

            return jsonify({
                'title': info.get('title', 'Video Downloader'),
                'thumbnail': info.get('thumbnail', ''),
                'preview_url': preview_url,
                'preview_type': 'video',
                'formats': formats
            })
    except Exception as e:
        return jsonify({'error': f"عذراً، الرابط غير مدعوم أو محمي من قبل المنصة."}), 500

@app.route('/download_video')
def download_video():
    url = request.args.get('url')
    file_id = str(uuid.uuid4())
    filepath = os.path.join('downloads', f"{file_id}.%(ext)s")
    
    dl_opts = dict(YDL_BASE_OPTS)
    
    # 🪄 السحر هنا: إجبار yt-dlp على تحميل الفيديوهات بصيغة (H.264/AVC) المتوافقة مع ويندوز
    dl_opts.update({
        'format': 'bestvideo[vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/best[vcodec^=avc][ext=mp4]/best[ext=mp4]/best',
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

        return send_file(final_filepath, as_attachment=True, download_name="Video.mp4")
        
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
