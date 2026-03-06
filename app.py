import os
import re
import time
import uuid
import threading
import logging
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
import imageio_ffmpeg

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_AGE_SECONDS = 2 * 60 * 60          # 2 hours
CLEANUP_INTERVAL_SECONDS = 10 * 60     # 10 minutes

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Background cleanup daemon
# ---------------------------------------------------------------------------

def _cleanup_loop():
    """Permanently delete files in downloads/ older than MAX_AGE_SECONDS."""
    while True:
        try:
            now = time.time()
            for p in DOWNLOAD_DIR.iterdir():
                if p.is_file() and (now - p.stat().st_mtime) > MAX_AGE_SECONDS:
                    p.unlink(missing_ok=True)
                    logger.info("Cleanup: deleted %s", p.name)
        except Exception as exc:
            logger.warning("Cleanup error: %s", exc)
        time.sleep(CLEANUP_INTERVAL_SECONDS)


threading.Thread(target=_cleanup_loop, daemon=True).start()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE = re.compile(r'[^A-Za-z0-9_\-.]')


def _safe_filename(title: str, ext: str = "mp4") -> str:
    """Return a filesystem-safe filename with a short UUID suffix."""
    base = _SAFE.sub("_", title)[:80]
    short_id = uuid.uuid4().hex[:8]
    return f"{base}_{short_id}.{ext}"


def _requires_transcode(filepath: str) -> bool:
    """Run FFmpeg to check the actual video codec. Return True if it is NOT H.264."""
    import subprocess
    # ffmpeg -i returns 1 because no output file is specified, but prints info to stderr
    result = subprocess.run([FFMPEG_PATH, "-i", filepath], capture_output=True, text=True)
    stderr = result.stderr.lower()
    
    # Simple check for stream info
    if "video: hevc" in stderr or "video: vp9" in stderr or "video: av1" in stderr:
        return True
    
    # If it explicitly says h264, we don't need to transcode
    if "video: h264" in stderr or "video: avc" in stderr:
        return False
        
    # Default to transcoding if unknown to be safe
    return True


def _remux_to_mp4(src: str, dst: str, force_transcode: bool = False):
    """Re-mux *src* into an mp4 container with faststart, and optionally transcode video to h264."""
    import subprocess
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", src,
    ]
    if force_transcode:
        # Transcode video to H.264 (AVC) for maximum browser/player compatibility, but keep audio logic simple
        cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac"])
    else:
        # Fast copy
        cmd.extend(["-c", "copy"])

    cmd.extend(["-movflags", "+faststart", dst])
    import logging
    logging.getLogger("streamvault").info("FFmpeg running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
    if result.returncode != 0:
        logging.getLogger("streamvault").error("FFmpeg error: %s", result.stderr)
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")
    else:
        logging.getLogger("streamvault").info("FFmpeg success. force_transcode=%s", force_transcode)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "No URL provided."}), 400

    # Unique temp name to avoid collisions
    temp_id = uuid.uuid4().hex[:10]
    temp_template = str(DOWNLOAD_DIR / f"tmp_{temp_id}.%(ext)s")

    ydl_opts = {
        # Broad format fallback: prefer mp4 streams → any merged → single best
        "format": (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[ext=mp4]+bestaudio/"
            "bestvideo+bestaudio/"
            "best[ext=mp4]/"
            "best"
        ),
        # Prioritize H.264 video codec to prevent "Missing HEVC Codec" errors
        "format_sort": ["vcodec:h264"],
        "outtmpl": temp_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        "http_chunk_size": 10485760,           # 10 MB chunks
        "ffmpeg_location": FFMPEG_PATH,
        # Pretend to be a real browser (TLS impersonation via curl_cffi for TikTok etc)
        "impersonate": ImpersonateTarget(client="chrome"),
        # YouTube-specific: use android_vr client (no JS runtime needed)
        "extractor_args": {
            "youtube": {
                "player_client": ["android_vr"],
                "skip": ["js"],
            },
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            raw_title = info.get("title", "video") or "video"
            # Strip problematic unicode chars (like TikTok emojis) that can crash the response
            title = raw_title.encode("utf-8", "ignore").decode("utf-8")
            duration = info.get("duration")

            # yt-dlp may produce the file with the final ext already
            # Find the downloaded file
            downloaded = None
            for p in DOWNLOAD_DIR.iterdir():
                if p.name.startswith(f"tmp_{temp_id}"):
                    downloaded = p
                    break

            if downloaded is None:
                return jsonify({"error": "Download succeeded but file not found."}), 500

            # Build final safe filename
            final_name = _safe_filename(title)
            final_path = DOWNLOAD_DIR / final_name

            # Detect actual codec by probing the file with FFmpeg, bypassing buggy yt-dlp metadata
            needs_transcode = _requires_transcode(str(downloaded))

            # Remux into mp4 with faststart, and transcode if necessary
            if downloaded.suffix.lower() != ".mp4" or needs_transcode:
                _remux_to_mp4(str(downloaded), str(final_path), force_transcode=needs_transcode)
                downloaded.unlink(missing_ok=True)
            else:
                # Even if mp4 and h264, re-mux to ensure faststart flag (web optimized)
                _remux_to_mp4(str(downloaded), str(final_path), force_transcode=False)
                downloaded.unlink(missing_ok=True)

            size_mb = round(final_path.stat().st_size / (1024 * 1024), 2)

            return jsonify({
                "filename": final_name,
                "title": title,
                "duration": duration,
                "size_mb": size_mb,
            })

    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc)
        if "403" in msg or "Forbidden" in msg:
            return jsonify({"error": "Access forbidden (403). The video may be private or geo-restricted."}), 403
        if "404" in msg or "not found" in msg.lower():
            return jsonify({"error": "Video not found (404). Please check the URL."}), 404
        return jsonify({"error": f"Download failed: {msg}"}), 500
    except Exception as exc:
        logger.exception("Unexpected error during download")
        return jsonify({"error": f"An unexpected error occurred: {exc}"}), 500


@app.route("/stream/<filename>")
def stream(filename):
    # Sanitize – prevent directory traversal
    safe = Path(filename).name
    filepath = DOWNLOAD_DIR / safe

    if not filepath.exists():
        return jsonify({"error": "File not found."}), 404

    as_dl = request.args.get("dl") == "1"
    return send_file(
        filepath,
        mimetype="video/mp4",
        as_attachment=as_dl,
        download_name=safe,
        conditional=True,
    )

# ---------------------------------------------------------------------------
# Entrypoint – Waitress in production, Flask dev server locally
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info("Starting server on port %d …", port)

    if os.environ.get("RENDER"):
        from waitress import serve
        serve(app, host="0.0.0.0", port=port, threads=4)
    else:
        # Local development – also use waitress for consistency
        try:
            from waitress import serve
            serve(app, host="0.0.0.0", port=port, threads=4)
        except ImportError:
            app.run(host="0.0.0.0", port=port, debug=True)
