"""
video_downloader.py
Asynchronously downloads videos from YouTube, TikTok, Twitter, or direct web links
using yt-dlp (with fallback to urllib for direct media files).
"""
import os
import re
import urllib.request
from PyQt5.QtCore import QThread, pyqtSignal

import yt_dlp
import yt_dlp.extractor


def strip_ansi(text: str) -> str:
    """Removes ANSI color codes from terminal output strings."""
    return re.sub(r'\x1b\[[0-9;]*m', '', text).strip()


class VideoDownloaderThread(QThread):
    download_finished = pyqtSignal(str)  # Emits downloaded local file path
    download_failed = pyqtSignal(str)    # Emits error message string

    def __init__(self, url: str, output_dir: str):
        super().__init__()
        self.url = url.strip()
        self.output_dir = output_dir

    def run(self):
        if not self.url:
            self.download_failed.emit("URL cannot be empty.")
            return

        os.makedirs(self.output_dir, exist_ok=True)
        yt_err = ""

        # Attempt 1: yt-dlp (handles YouTube, TikTok, Twitter, direct MP4/WebM, etc.)
        try:
            ydl_opts = {
                'outtmpl': os.path.join(self.output_dir, '%(title)s_%(id)s.%(ext)s'),
                'format': 'bestvideo/best',
                'noplaylist': True,
                'extractor_args': {'youtube': {'player_client': ['mweb', 'android', 'ios', 'tv']}},
                'no_color': True,
                'quiet': True,
                'no_warnings': True,
                'overwrites': False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                filepath = None
                if info and info.get('requested_downloads'):
                    filepath = info['requested_downloads'][0].get('filename')
                if not filepath or not os.path.exists(filepath):
                    filepath = ydl.prepare_filename(info)

                if filepath and os.path.exists(filepath):
                    self.download_finished.emit(filepath)
                    return
        except Exception as e:
            yt_err = strip_ansi(str(e))

        # Attempt 2: Direct HTTP download fallback for direct file URLs (.mp4, .mov, etc.)
        try:
            clean_url = self.url.split('?')[0]
            ext = os.path.splitext(clean_url)[1].lower()
            if ext in {".mp4", ".mov", ".webm", ".avi", ".mkv", ".gif", ".png", ".webp"}:
                filename = f"downloaded_{abs(hash(self.url)) % 1000000}{ext}"
                filepath = os.path.join(self.output_dir, filename)
                req = urllib.request.Request(
                    self.url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(req) as resp, open(filepath, 'wb') as out_f:
                    out_f.write(resp.read())

                if os.path.exists(filepath):
                    self.download_finished.emit(filepath)
                    return
        except Exception as e:
            pass

        msg = yt_err if yt_err else "Invalid or unreachable video URL."
        self.download_failed.emit(f"Could not download video link.\n\nReason: {msg}\n\nPlease make sure the video link is active and public.")
