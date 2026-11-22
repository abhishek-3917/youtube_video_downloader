"""
Command-Line Interface (CLI) for YouTube Studio Downloader
Usage:
  python cli.py <URL> [OPTIONS]
  python cli.py --interactive
"""

import sys
import os
import argparse
import core_downloader

def print_banner():
    print("=" * 65)
    print("  YouTube Studio Downloader (Lossless & Zero Size Limit)")
    print("=" * 65)

def format_progress_cli(data: dict):
    status = data.get("status")
    prog = data.get("progress", 0.0)
    speed = data.get("speed", "--")
    size = f"{data.get('downloaded_formatted', '--')} / {data.get('total_formatted', '--')}"
    eta = data.get("eta", "--")

    bar_len = 30
    filled = int(bar_len * (prog / 100.0))
    bar = "█" * filled + "░" * (bar_len - filled)

    if status == "downloading":
        sys.stdout.write(f"\r[{bar}] {prog:5.1f}% | {speed:<12} | {size:<18} | ETA: {eta:<6}")
        sys.stdout.flush()
    elif status == "merging":
        sys.stdout.write("\r[Muxing streams with ffmpeg -c copy (Zero Compression)]...              \n")
        sys.stdout.flush()
    elif status == "finished":
        sys.stdout.write("\r[✓ Complete] Download finished successfully!                           \n")
        sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(description="Download YouTube videos and audio at maximum quality without compression.")
    parser.add_argument("url", nargs="?", help="YouTube video URL")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive format selector")
    parser.add_argument("-q", "--quality", default="best", help="Video resolution (e.g. 4320, 2160, 1440, 1080, 720, 480 or best)")
    parser.add_argument("-c", "--container", default="mp4", choices=["mp4", "mkv", "webm"], help="Target container (default: mp4)")
    parser.add_argument("-a", "--audio-only", action="store_true", help="Download audio only")
    parser.add_argument("--audio-format", default="best_audio_original", 
                        choices=["best_audio_original", "wav", "flac", "mp3", "m4a", "opus"],
                        help="Audio preset (default: best_audio_original untouched)")
    parser.add_argument("-f", "--format-id", help="Exact yt-dlp format ID to download")
    parser.add_argument("-o", "--output-dir", default=core_downloader.DEFAULT_DOWNLOAD_DIR, help="Destination directory")
    parser.add_argument("--embed-thumbnail", action="store_true", help="Embed thumbnail image into video")
    parser.add_argument("--embed-subtitles", action="store_true", help="Embed subtitles into video")
    parser.add_argument("--cookies", help="Path to cookies.txt file to bypass YouTube bot detection")
    parser.add_argument("--cookies-from-browser", choices=["chrome", "edge", "firefox", "brave"], help="Extract cookies directly from your browser")
    parser.add_argument("-l", "--list-formats", action="store_true", help="List all available video and audio streams and exit")

    args = parser.parse_args()

    print_banner()

    url = args.url
    if not url:
        url = input("\nEnter YouTube URL: ").strip()
        if not url:
            print("No URL provided. Exiting.")
            sys.exit(1)

    print(f"\nAnalyzing video metadata for: {url}...")
    try:
        info = core_downloader.fetch_video_info(url, cookiefile=args.cookies, browser=args.cookies_from_browser)
    except Exception as e:
        print(f"\nError fetching video info: {e}")
        sys.exit(1)

    print(f"\nTitle:    {info.get('title')}")
    print(f"Channel:  {info.get('channel')}")
    print(f"Duration: {info.get('formatted_duration')}")
    print(f"Views:    {info.get('view_count')}")

    if args.list_formats:
        print("\n" + "=" * 50)
        print("AVAILABLE VIDEO STREAMS:")
        print("=" * 50)
        for s in info.get("video_streams", []):
            print(f"ID: {s['format_id']:<6} | {s['quality_label']:<10} | {s['fps']}fps | {s['vcodec']:<18} | Size: {s['formatted_size']}")

        print("\n" + "=" * 50)
        print("AVAILABLE AUDIO PRESETS:")
        print("=" * 50)
        for p in info.get("audio_presets", []):
            lossless_tag = "[LOSSLESS]" if p.get("lossless") else "[HIGH QUALITY]"
            print(f"Preset: {p['id']:<22} | {lossless_tag} {p['name']}")
        return

    options = {
        "download_dir": args.output_dir,
        "container": args.container,
        "embed_thumbnail": args.embed_thumbnail,
        "embed_subtitles": args.embed_subtitles,
        "cookiefile": args.cookies,
        "browser": args.cookies_from_browser
    }

    if args.interactive:
        print("\nChoose download type:")
        print("  [1] Best Available Video + Audio (Max Resolution, Lossless Stream-Copy)")
        print("  [2] Select specific Video Resolution")
        print("  [3] Audio Only (Untouched Source Stream)")
        print("  [4] Audio Only (Lossless WAV uncompressed)")
        print("  [5] Audio Only (Lossless FLAC)")
        print("  [6] Audio Only (MP3 320kbps)")
        choice = input("Enter choice [1-6] (default: 1): ").strip() or "1"

        if choice == "1":
            options["mode"] = "video"
            options["quality"] = "best"
        elif choice == "2":
            options["mode"] = "video"
            streams = info.get("video_streams", [])
            for idx, s in enumerate(streams):
                print(f"  [{idx+1}] {s['quality_label']} ({s['fps']}fps, {s['vcodec']}) ~ {s['formatted_size']}")
            s_idx = input(f"Select stream [1-{len(streams)}]: ").strip()
            try:
                selected_stream = streams[int(s_idx) - 1]
                options["format_id"] = selected_stream["format_id"]
            except Exception:
                options["quality"] = "best"
        elif choice == "3":
            options["mode"] = "audio"
            options["audio_preset"] = "best_audio_original"
        elif choice == "4":
            options["mode"] = "audio"
            options["audio_preset"] = "wav_lossless"
        elif choice == "5":
            options["mode"] = "audio"
            options["audio_preset"] = "flac_lossless"
        elif choice == "6":
            options["mode"] = "audio"
            options["audio_preset"] = "mp3_320"
    else:
        if args.audio_only:
            options["mode"] = "audio"
            options["audio_preset"] = args.audio_format
        elif args.format_id:
            options["mode"] = "custom"
            options["format_id"] = args.format_id
        else:
            options["mode"] = "video"
            options["quality"] = args.quality

    print(f"\nSaving to: {os.path.abspath(options['download_dir'])}")
    print("Initiating download (No compression, no size limit)...\n")

    task = core_downloader.DownloadTask("cli-task", url, options)
    core_downloader.execute_download(task, format_progress_cli)

    if task.status == "finished":
        print(f"\nSuccess! File saved at:\n{task.filepath}")
    else:
        print(f"\nFailed: {task.error_message}")

if __name__ == "__main__":
    main()
