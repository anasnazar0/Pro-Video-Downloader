import os
import uuid
import subprocess
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
    'format_sort': ['vcodec:h264', 'res', 'ext:mp4:m4a'], 
    'extractor_args': {'youtube': ['player_client=android,ios']},
    # 👇 هذا هو السطر السحري الجديد
    'cookiefile': 'cookies.txt',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
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

    try:
        with yt_dlp.YoutubeDL(YDL_BASE_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = []
            raw_formats = info.get('formats', [])
            
            preview_url = None
            preview_type = 'video' # النوع الافتراضي يوتيوب/تويتر
            
            # 🚀 الحل الجذري والنهائي لمشكلة عرض تيك توك
            if 'tiktok.com' in url.lower():
                video_id = info.get('id')
                # استخدام مشغل تيك توك الرسمي (لا يوجد فيه حظر 403 أبداً)
                preview_url = f"https://www.tiktok.com/embed/v2/{video_id}"
                preview_type = 'iframe'
            else:
                # لبقية المواقع (يوتيوب وتويتر)
                raw_preview = None
                if raw_formats:
                    h264_formats = [f for f in raw_formats if f.get('vcodec') != 'none' and ('h265' not in f.get('vcodec', '').lower() and 'hevc' not in f.get('vcodec', '').lower())]
                    if h264_formats:
                        combined = [f for f in h264_formats if f.get('acodec') != 'none' and f.get('ext') == 'mp4']
                        if combined:
                            raw_preview = combined[-1].get('url')
                        else:
                            raw_preview = h264_formats[-1].get('url')
                    else:
                        raw_preview = info.get('url')
                else:
                    raw_preview = info.get('url')
                
                preview_url = raw_preview
                preview_type = 'video'

            if not raw_formats:
                formats.append({
                    'id': 'best',
                    'resolution': 'Best Quality',
                    'ext': 'mp4',
                    'url': f'/download_video?url={url}&format_id=best'
                })
            else:
                for f in raw_formats:
                    if f.get('vcodec') == 'none':
                        continue
                    
                    vcodec = f.get('vcodec', '').lower()
                    if 'h265' in vcodec or 'hevc' in vcodec:
                        continue
                        
                    formats.append(f)
                
                formats.sort(key=lambda x: x.get('height') or 0, reverse=True)
                
                final_formats = []
                unique_resolutions = set()
                
                for f in formats:
                    height = f.get('height')
                    res_str = f"{height}p" if height else (f.get('resolution') or 'Standard')
                        
                    if res_str not in unique_resolutions:
                        unique_resolutions.add(res_str)
                        final_formats.append({
                            'id': f.get('format_id'),
                            'resolution': res_str,
                            'ext': 'mp4',
                            'url': f'/download_video?url={url}&format_id={f.get("format_id")}'
                        })
                        
                    if len(final_formats) >= 5:
                        break

            return jsonify({
                'title': info.get('title', 'Video'),
                'thumbnail': info.get('thumbnail'),
                'preview_url': preview_url, 
                'preview_type': preview_type, # إرسال نوع المشغل للواجهة
                'formats': final_formats
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download_video')
def download_video():
    url = request.args.get('url')
    format_id = request.args.get('format_id', 'best')
    
    file_id = str(uuid.uuid4())
    filepath = os.path.join('downloads', f"{file_id}.%(ext)s")
    
    dl_opts = dict(YDL_BASE_OPTS)
    
    if 'tiktok.com' in url.lower():
        dl_opts['format'] = 'bestvideo[vcodec^=avc]+bestaudio/best[vcodec^=avc]/best'
    elif format_id == 'best':
        dl_opts['format'] = 'bestvideo[vcodec!*=hevc][vcodec!*=h265]+bestaudio/best[vcodec!*=hevc][vcodec!*=h265]/best'
    else:
        dl_opts['format'] = f'{format_id}+bestaudio/best'
        
    dl_opts.update({
        'outtmpl': filepath,
        'merge_output_format': 'mp4',
    })
    
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([url])
        
        final_filepath = None
        for file in os.listdir('downloads'):
            if file.startswith(file_id) and file.endswith('.mp4'):
                final_filepath = os.path.join('downloads', file)
                break
                
        if not final_filepath or not os.path.exists(final_filepath):
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
            except Exception as e:
                pass
            return response

        return send_file(final_filepath, as_attachment=True, download_name="video.mp4")
        
    except Exception as e:
        return f"Error: {str(e)}", 500


if __name__ == '__main__':
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("\n✅ FFmpeg is Ready!")
    except Exception:
        print("\n❌ FFmpeg not found! Please check its location.")
        pass
        

    app.run(debug=True, port=5000)


