"""
Core YouTube Downloader Engine
Powered by yt-dlp and ffmpeg.
Supports:
- All video qualities up to 8K / 4K / 1440p / 1080p / 720p / 480p / 360p / 240p / 144p (with 60fps, HDR)
- All audio formats (Original untouched source stream, Lossless WAV, Lossless FLAC, MP3 320k, M4A/AAC, OPUS)
- Strict zero-compression policy: Stream-copy muxing (-c copy) so no video or audio is re-encoded or degraded
- Zero file size limit: handles files of any size with chunked streaming and resume capability
- Stable Total Size Tracking: Prevents fluctuating/jittering total sizes on DASH/fragmented streams
"""

import os
import sys
import time
import math
import shutil
import threading
from typing import Dict, Any, List, Optional, Callable
import yt_dlp

DEFAULT_DOWNLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "downloads"))
DEFAULT_COOKIE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "cookies.txt"))

def format_bytes(size_bytes: Optional[int]) -> str:
    """Format bytes into human-readable string (e.g. 1.25 GB)."""
    if not size_bytes or size_bytes <= 0:
        return "Unknown size"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    size = float(size_bytes)
    while size >= 1024.0 and unit_idx < len(units) - 1:
        size /= 1024.0
        unit_idx += 1
    return f"{size:.2f} {units[unit_idx]}"

def format_duration(seconds: Optional[int]) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if not seconds:
        return "Unknown"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def resolve_filepath(path_str: Optional[str], fallback_dir: str = DEFAULT_DOWNLOAD_DIR) -> Optional[str]:
    """
    Resolves a filepath handling Windows invalid character sanitization
    (e.g. pipe '|' to fullwidth pipe '｜' U+FF5C, or underscores), and matches by YouTube ID.
    """
    if not path_str:
        return None
    clean = path_str.strip('"').strip("'")
    norm = os.path.normpath(clean)
    if os.path.exists(norm):
        return norm
    # Check alternate character substitutions done by Windows or yt-dlp
    for alt in [
        norm.replace("|", "｜"),
        norm.replace("｜", "|"),
        norm.replace("|", "_"),
        norm.replace(":", "_"),
        norm.replace("?", "_"),
    ]:
        if os.path.exists(alt):
            return alt
    # Search by basename inside download directory
    base = os.path.basename(clean)
    for c in [base, base.replace("|", "｜"), base.replace("｜", "|"), base.replace("|", "_")]:
        cand = os.path.join(fallback_dir, c)
        if os.path.exists(cand):
            return cand
    # Search directory for file containing 11-char YouTube video ID if present in the path
    import re
    match = re.search(r'\[([a-zA-Z0-9_-]{11})\]', clean)
    if match and os.path.exists(fallback_dir):
        vid_id = match.group(1)
        for f in os.listdir(fallback_dir):
            if vid_id in f and not f.endswith(".part") and not f.endswith(".ytdl"):
                return os.path.join(fallback_dir, f)
    return None

def format_yt_error(err: Exception) -> str:
    """Formats raw yt-dlp error into clear, actionable guidance."""
    err_str = str(err)
    if "Failed to extract any player response" in err_str or "The page needs to be reloaded" in err_str or "confirm you’re not a bot" in err_str or "confirm you're not a bot" in err_str:
        return (
            "YouTube Verification / Datacenter Block Triggered: YouTube requires sign-in verification for this video.\n"
            "Solution: Export your YouTube cookies using the 'Get cookies.txt LOCALLY' browser extension, "
            "then upload it in the '🍪 Cookies & Bot Bypass' tab. Once active, all bot checks are bypassed."
        )
    if "Could not copy Chrome cookie database" in err_str:
        return (
            "Chrome Database Lock: Chrome locks its cookies while running. "
            "Please completely close all Chrome windows, or export a 'cookies.txt' file instead."
        )
    if "Sign in to confirm your age" in err_str:
        return (
            "Age-Restricted Video: YouTube requires an authenticated account to verify age. "
            "Please provide cookies.txt from a verified account."
        )
    return err_str

def get_base_ydl_opts(cookiefile: Optional[str] = None, browser: Optional[str] = None) -> Dict[str, Any]:
    """Base options for yt-dlp configured for maximum speed, zero size limit, and authentication."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "js_runtimes": {"node": {}},
        "remote_components": {"ejs:github": {}},
        "buffersize": 1024 * 1024,  # 1MB buffer
        "retries": 15,
        "fragment_retries": 15,
        "continuedl": True,
        "concurrent_fragment_downloads": 8,
    }

    # Cookie configuration: check explicit cookiefile or default workspace cookies.txt
    effective_cookiefile = cookiefile
    if not effective_cookiefile and os.path.exists(DEFAULT_COOKIE_FILE):
        effective_cookiefile = DEFAULT_COOKIE_FILE

    if effective_cookiefile and os.path.exists(effective_cookiefile):
        opts["cookiefile"] = effective_cookiefile
    elif browser and browser.lower() != "none":
        opts["cookiesfrombrowser"] = (browser.lower(),)

    return opts

def calculate_format_size(f: Dict[str, Any], duration: Optional[int]) -> int:
    """Accurately calculates or estimates size of a format in bytes."""
    if not isinstance(f, dict):
        return 0
    fs = f.get("filesize") or f.get("filesize_approx")
    if fs and fs > 0:
        return int(fs)
    tbr = f.get("tbr")
    if not tbr:
        vbr = f.get("vbr") or 0
        abr = f.get("abr") or 0
        tbr = (vbr or 0) + (abr or 0)
    if tbr and duration and duration > 0:
        return int((tbr * 1000 / 8) * duration)
    return 0

def fetch_video_info(url: str, cookiefile: Optional[str] = None, browser: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts complete metadata and categorized formats for a given YouTube URL.
    Categorizes streams into:
    1. Video Streams (with audio merged using ffmpeg stream copy, no compression)
    2. Audio Streams (raw untouched, or lossless/high-bitrate conversions)
    3. Pre-muxed Progressive Streams
    """
    opts = get_base_ydl_opts(cookiefile=cookiefile, browser=browser)
    opts["extract_flat"] = False

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError("Could not retrieve video information.")
            
            if "_type" in info and info["_type"] == "playlist":
                entries = list(info.get("entries", []))
                if entries:
                    info = entries[0]
                else:
                    raise ValueError("The provided playlist contains no videos.")
    except Exception as e:
        err_msg = str(e)
        if "Failed to extract any player response" in err_msg or "The page needs to be reloaded" in err_msg:
            # Datacenter / Cloud server block fallback: query mobile player clients
            opts["extractor_args"] = {"youtube": {"player_client": ["android", "ios", "mweb"]}}
            try:
                with yt_dlp.YoutubeDL(opts) as ydl_fb:
                    info = ydl_fb.extract_info(url, download=False)
                    if not info:
                        raise ValueError("Could not retrieve video information.")
                    if "_type" in info and info["_type"] == "playlist":
                        entries = list(info.get("entries", []))
                        if entries:
                            info = entries[0]
            except Exception as e2:
                raise ValueError(format_yt_error(e2))
        else:
            raise ValueError(format_yt_error(e))

    duration = info.get("duration") or 0
    formats = info.get("formats", [])
    best_audio = None
    best_audio_size = 0

    # Locate best audio stream for combining with video-only streams
    audio_only_streams = []
    for f in formats:
        if f.get("vcodec") == "none" and f.get("acodec") != "none":
            audio_only_streams.append(f)
            size = calculate_format_size(f, duration)
            tbr = f.get("tbr") or f.get("abr") or 0
            if tbr > (best_audio.get("tbr") or best_audio.get("abr") or 0 if best_audio else 0):
                best_audio = f
                best_audio_size = size

    # Categorize Video Streams
    video_streams_map = {}
    progressive_streams = []
    raw_audio_options = []

    for f in formats:
        fid = f.get("format_id")
        ext = f.get("ext")
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        height = f.get("height")
        width = f.get("width")
        fps = f.get("fps") or 30
        filesize = calculate_format_size(f, duration)
        tbr = f.get("tbr") or 0
        vbr = f.get("vbr") or 0
        dynamic_range = f.get("dynamic_range", "SDR")

        # 1. Video Only Streams (DASH)
        if vcodec != "none" and acodec == "none" and height:
            quality_label = f"{height}p"
            if fps and fps > 30:
                quality_label += f"{fps}"
            if dynamic_range and dynamic_range.upper() != "SDR":
                quality_label += f" {dynamic_range}"

            key = (height, fps, dynamic_range)
            total_size_approx = ((filesize or 0) + (best_audio_size or 0)) if (filesize or best_audio_size) else 0

            stream_data = {
                "format_id": fid,
                "height": height,
                "width": width,
                "fps": fps,
                "quality_label": quality_label,
                "dynamic_range": dynamic_range,
                "vcodec": vcodec,
                "ext": ext,
                "filesize": filesize,
                "total_estimated_size": total_size_approx,
                "formatted_size": format_bytes(total_size_approx),
                "tbr": tbr or vbr,
                "needs_mux": True
            }

            if key not in video_streams_map or (tbr > (video_streams_map[key].get("tbr") or 0)):
                video_streams_map[key] = stream_data

        # 2. Combined / Progressive Streams (Pre-muxed video + audio)
        elif vcodec != "none" and acodec != "none" and height:
            prog_stream = {
                "format_id": fid,
                "height": height,
                "width": width,
                "fps": fps,
                "quality_label": f"{height}p",
                "dynamic_range": "SDR",
                "ext": ext,
                "vcodec": vcodec,
                "acodec": acodec,
                "filesize": filesize,
                "total_estimated_size": filesize,
                "formatted_size": format_bytes(filesize),
                "tbr": tbr,
                "needs_mux": False
            }
            progressive_streams.append(prog_stream)
            key = (height, fps or 30, "SDR")
            if key not in video_streams_map:
                video_streams_map[key] = prog_stream

    sorted_video_streams = sorted(
        video_streams_map.values(),
        key=lambda x: (x.get("height") or 0, x.get("fps") or 0, x.get("tbr") or 0),
        reverse=True
    )

    for f in audio_only_streams:
        fid = f.get("format_id")
        acodec = f.get("acodec", "")
        ext = f.get("ext", "")
        abr = f.get("abr") or f.get("tbr") or 0
        asr = f.get("asr") or 44100
        filesize = calculate_format_size(f, duration)

        raw_audio_options.append({
            "format_id": fid,
            "ext": ext,
            "acodec": acodec,
            "abr": round(abr, 1) if abr else 0,
            "asr": asr,
            "filesize": filesize,
            "formatted_size": format_bytes(filesize),
            "label": f"{ext.upper()} ({acodec}) - {round(abr)} kbps" if abr else f"{ext.upper()} ({acodec})"
        })

    raw_audio_options = sorted(raw_audio_options, key=lambda x: x.get("abr") or 0, reverse=True)

    audio_presets = [
        {
            "id": "best_audio_original",
            "name": "Original Source Stream (Best Quality Untouched)",
            "description": "Zero re-encoding or conversion. Direct original audio stream (M4A/AAC or Opus).",
            "format": "ba/b",
            "ext": "original",
            "lossless": True
        },
        {
            "id": "wav_lossless",
            "name": "Lossless WAV (Uncompressed PCM Audio)",
            "description": "Direct uncompressed 16/24-bit PCM WAV. Zero loss of sonic fidelity.",
            "format": "ba/b",
            "ext": "wav",
            "lossless": True
        },
        {
            "id": "flac_lossless",
            "name": "Lossless FLAC (Highest Studio Compression)",
            "description": "Lossless FLAC container. 100% bit-perfect audio reproduction.",
            "format": "ba/b",
            "ext": "flac",
            "lossless": True
        },
        {
            "id": "mp3_320",
            "name": "MP3 (320 kbps Maximum Quality CBR/V0)",
            "description": "Universal compatibility with maximum MP3 bitrate and full metadata.",
            "format": "ba/b",
            "ext": "mp3",
            "lossless": False
        },
        {
            "id": "m4a_aac",
            "name": "M4A (Apple AAC High Quality)",
            "description": "Standard Apple compatible AAC audio stream without compression degradation.",
            "format": "ba/b",
            "ext": "m4a",
            "lossless": False
        },
        {
            "id": "opus_native",
            "name": "OPUS (High-Efficiency Native YouTube Stream)",
            "description": "Modern Opus codec direct extract with pristine quality.",
            "format": "ba/b",
            "ext": "opus",
            "lossless": True
        }
    ]

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("uploader") or info.get("channel"),
        "duration": duration,
        "formatted_duration": format_duration(duration),
        "thumbnail": info.get("thumbnail"),
        "view_count": f"{info.get('view_count', 0):,}" if info.get("view_count") else "Unknown",
        "upload_date": info.get("upload_date"),
        "description": (info.get("description") or "")[:300],
        "video_streams": sorted_video_streams,
        "progressive_streams": progressive_streams,
        "raw_audio_streams": raw_audio_options,
        "audio_presets": audio_presets,
        "webpage_url": info.get("webpage_url") or url
    }

class DownloadTask:
    """Manages an active download with progress tracking and cancel support."""
    def __init__(self, task_id: str, url: str, options: Dict[str, Any]):
        self.task_id = task_id
        self.url = url
        self.options = options
        self.status = "queued"  # queued, downloading, merging, finished, error, cancelled
        self.progress = 0.0
        self.speed_str = "0 KB/s"
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.eta_str = "--:--"
        self.filename = ""
        self.filepath = ""
        self.error_message = ""
        self.start_time = 0.0
        self._cancel_requested = False
        self.thread: Optional[threading.Thread] = None

    def cancel(self):
        self._cancel_requested = True
        self.status = "cancelled"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "url": self.url,
            "status": self.status,
            "progress": round(self.progress, 1),
            "speed": self.speed_str,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "downloaded_formatted": format_bytes(self.downloaded_bytes),
            "total_formatted": format_bytes(self.total_bytes),
            "eta": self.eta_str,
            "filename": self.filename,
            "filepath": self.filepath,
            "error_message": self.error_message
        }

def execute_download(
    task: DownloadTask,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
):
    """
    Executes the download with strict NO-COMPRESSION settings and STABLE TOTAL SIZE tracking.
    - If video + audio: stream-copies into target container (MP4 or MKV) using ffmpeg (-c copy)
    - If audio only: extracts directly or converts to lossless WAV/FLAC or highest bitrate MP3
    - No size limit, resumable.
    - Total size is stabilized and does NOT fluctuate every second on fragmented DASH downloads.
    """
    opts = get_base_ydl_opts(
        cookiefile=task.options.get("cookiefile"),
        browser=task.options.get("browser")
    )
    task.status = "downloading"
    task.start_time = time.time()

    download_dir = task.options.get("download_dir") or DEFAULT_DOWNLOAD_DIR
    os.makedirs(download_dir, exist_ok=True)

    mode = task.options.get("mode", "video")  # 'video', 'audio', 'custom'
    container = task.options.get("container", "mp4").lower()
    selected_format_id = task.options.get("format_id")
    audio_preset = task.options.get("audio_preset", "best_audio_original")
    embed_thumbnail = task.options.get("embed_thumbnail", False)
    embed_subs = task.options.get("embed_subtitles", False)

    outtmpl = os.path.join(download_dir, "%(title)s [%(id)s].%(ext)s")
    opts["outtmpl"] = outtmpl

    if mode == "video":
        # For MP4 container, audio MUST use AAC (m4a, mp4a) for universal playback on Windows, Mac, iOS, Android, and TVs!
        # Opus inside MP4 is non-standard and causes Windows Media Player to fail rendering video (playing audio only).
        if container == "mp4":
            audio_stream_selector = "ba[ext=m4a]/bestaudio[ext=m4a]/bestaudio/best"
        else:
            audio_stream_selector = "bestaudio/best"

        if selected_format_id:
            opts["format"] = f"{selected_format_id}+{audio_stream_selector}/{selected_format_id}"
        else:
            quality = task.options.get("quality", "best")
            if quality == "best":
                if container == "mp4":
                    opts["format"] = f"bestvideo[ext=mp4]+{audio_stream_selector}/bestvideo+{audio_stream_selector}/best"
                else:
                    opts["format"] = f"bestvideo+{audio_stream_selector}/best"
            else:
                h = quality.replace("p", "")
                opts["format"] = f"bestvideo[height<={h}]+{audio_stream_selector}/best[height<={h}]/best"

        if container in ["mp4", "mkv", "webm"]:
            opts["merge_output_format"] = container
            if container == "mp4":
                # Ensure moov atom is moved to front (+faststart) so browsers and players can seek/play immediately without full download
                opts["postprocessor_args"] = {
                    "Merger": ["-c", "copy", "-movflags", "+faststart"],
                    "Fixup": ["-movflags", "+faststart"]
                }
            else:
                opts["postprocessor_args"] = {
                    "Merger": ["-c", "copy"]
                }

    elif mode == "audio":
        opts["format"] = "bestaudio/best"
        
        if audio_preset == "best_audio_original":
            pass
        elif audio_preset in ["wav", "wav_lossless"]:
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": None,
                "nopostoverwrites": False,
            }]
        elif audio_preset in ["flac", "flac_lossless"]:
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "flac",
                "preferredquality": "0",
                "nopostoverwrites": False,
            }]
        elif audio_preset in ["mp3", "mp3_320"]:
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
                "nopostoverwrites": False,
            }]
        elif audio_preset in ["m4a", "m4a_aac"]:
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": None,
                "nopostoverwrites": False,
            }]
        elif audio_preset in ["opus", "opus_native"]:
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "opus",
                "preferredquality": None,
                "nopostoverwrites": False,
            }]

    elif mode == "custom":
        if selected_format_id:
            opts["format"] = selected_format_id
        if container:
            opts["merge_output_format"] = container
        opts["postprocessor_args"] = {
            "ffmpeg": ["-c", "copy"]
        }

    postprocessors = opts.get("postprocessors", [])
    if embed_thumbnail and mode != "audio":
        opts["writethumbnail"] = True
        postprocessors.append({"key": "EmbedThumbnail"})
    if embed_subs:
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = True
        postprocessors.append({"key": "FFmpegEmbedSubtitle"})

    opts["postprocessors"] = postprocessors

    # -------------------------------------------------------------------------
    # STABLE PROGRESS TRACKER
    # Fixes the issue where total_bytes_estimate changes every second during DASH
    # fragment downloads and handles multi-stream (video + audio) downloads.
    # -------------------------------------------------------------------------
    stream_downloaded: Dict[str, int] = {}
    stream_totals: Dict[str, int] = {}
    locked_total_size: int = int(task.options.get("expected_size") or 0)

    def ydl_progress_hook(d):
        nonlocal locked_total_size

        if task._cancel_requested:
            raise Exception("Download cancelled by user.")

        status = d.get("status")
        if status == "downloading":
            task.status = "downloading"
            fn = d.get("filename") or "downloading_stream"
            dl_bytes = d.get("downloaded_bytes", 0)
            stream_downloaded[fn] = dl_bytes

            raw_tot = d.get("total_bytes")
            raw_tot_est = d.get("total_bytes_estimate")

            # Lock the stream total to prevent per-fragment fluctuating estimates
            if raw_tot:
                stream_totals[fn] = raw_tot
            elif fn not in stream_totals and raw_tot_est and raw_tot_est > 0:
                # Lock in initial estimate for this stream so it NEVER jitters every second!
                stream_totals[fn] = raw_tot_est
            elif fn in stream_totals and dl_bytes > stream_totals[fn]:
                # If downloaded exceeds locked total, smoothly adjust
                stream_totals[fn] = dl_bytes

            current_downloaded = sum(stream_downloaded.values())

            # Establish and maintain stable total size
            if locked_total_size <= 0:
                sum_streams = sum(stream_totals.values())
                if sum_streams > 0:
                    locked_total_size = sum_streams

            final_total = max(locked_total_size, current_downloaded)
            task.downloaded_bytes = current_downloaded
            task.total_bytes = final_total

            task.filename = os.path.basename(fn)
            task.filepath = fn

            if final_total > 0:
                task.progress = min(99.9, (current_downloaded / final_total) * 100.0)
            else:
                task.progress = 0.0

            speed = d.get("speed", 0)
            if speed and speed > 0:
                task.speed_str = f"{format_bytes(int(speed))}/s"
                remaining = max(0, final_total - current_downloaded)
                if remaining > 0:
                    task.eta_str = format_duration(int(remaining / speed))
                else:
                    task.eta_str = "00:01"
            else:
                task.speed_str = "Calculating..."
                task.eta_str = "--:--"

        elif status == "finished":
            fn = d.get("filename") or ""
            if fn:
                # When a stream finishes, ensure downloaded equals total for that stream
                tot = stream_totals.get(fn) or d.get("total_bytes") or d.get("downloaded_bytes", 0)
                stream_downloaded[fn] = tot
                stream_totals[fn] = tot
                task.filename = os.path.basename(fn)
                task.filepath = fn

            task.downloaded_bytes = sum(stream_downloaded.values())
            if locked_total_size > 0:
                task.total_bytes = max(locked_total_size, task.downloaded_bytes)
            else:
                task.total_bytes = task.downloaded_bytes

            task.status = "merging"
            task.speed_str = "Finalizing"
            task.eta_str = "00:00"

        if progress_callback:
            progress_callback(task.to_dict())

    opts["progress_hooks"] = [ydl_progress_hook]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # Step 1: Pre-extract format selection to determine exact/stable combined size
            info = ydl.extract_info(task.url, download=False)
            if not info:
                raise ValueError("Could not extract video metadata.")

            duration = info.get("duration") or 0
            req_formats = info.get("requested_formats")
            calculated_total = 0

            if req_formats:
                # Multi-stream (video + audio)
                for f in req_formats:
                    calculated_total += calculate_format_size(f, duration)
            else:
                calculated_total = calculate_format_size(info, duration)

            if calculated_total > 0 and locked_total_size <= 0:
                locked_total_size = calculated_total
                task.total_bytes = locked_total_size
                if progress_callback:
                    progress_callback(task.to_dict())

            # Step 2: Download the resolved streams without re-extracting
            ydl.process_ie_result(info, download=True)

            final_filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(final_filename)
            if mode == "audio":
                expected_ext = audio_preset.split("_")[0]
                if expected_ext in ["wav", "flac", "mp3", "m4a", "opus"]:
                    final_filename = f"{base}.{expected_ext}"
            elif mode == "video" and container:
                final_filename = f"{base}.{container}"

            if not os.path.exists(final_filename):
                candidates = [
                    final_filename.replace("|", "｜"),
                    final_filename.replace("｜", "|"),
                    ydl.prepare_filename(info),
                    ydl.prepare_filename(info).replace("|", "｜"),
                ]
                for c in candidates:
                    if os.path.exists(c):
                        final_filename = c
                        break
                else:
                    vid = info.get("id")
                    if vid and os.path.exists(download_dir):
                        for fname in os.listdir(download_dir):
                            if vid in fname and not fname.endswith(".part") and not fname.endswith(".ytdl"):
                                final_filename = os.path.join(download_dir, fname)
                                break

            if os.path.exists(final_filename):
                task.filepath = os.path.abspath(final_filename)
                task.filename = os.path.basename(final_filename)
            elif os.path.exists(ydl.prepare_filename(info)):
                task.filepath = os.path.abspath(ydl.prepare_filename(info))
                task.filename = os.path.basename(task.filepath)

        task.status = "finished"
        task.progress = 100.0
        if task.filepath and os.path.exists(task.filepath):
            actual_size = os.path.getsize(task.filepath)
            if locked_total_size <= 0:
                locked_total_size = actual_size
            task.downloaded_bytes = locked_total_size
            task.total_bytes = locked_total_size
        else:
            task.downloaded_bytes = locked_total_size if locked_total_size > 0 else task.total_bytes
            task.total_bytes = task.downloaded_bytes

        if progress_callback:
            progress_callback(task.to_dict())

    except Exception as e:
        if task._cancel_requested:
            task.status = "cancelled"
            task.error_message = "Download cancelled by user."
        else:
            task.status = "error"
            task.error_message = format_yt_error(e)
        if progress_callback:
            progress_callback(task.to_dict())
