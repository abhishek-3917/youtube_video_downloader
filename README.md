# YouTube Studio Downloader PRO

A high-performance YouTube video and audio downloader engineered for maximum quality preservation, zero compression, and unlimited download sizes.

---

## 🌟 Key Features

1. **Strict Zero-Compression Policy (Bit-for-Bit Stream Copy)**:
   - YouTube delivers high-resolution formats (1080p, 1440p 2K, 2160p 4K, 4320p 8K, 60fps, HDR) as separate video and audio streams.
   - Most standard tools transcode and degrade the file. This downloader uses native `ffmpeg` stream copying (`-c copy`) to mux the untouched video stream and audio stream into your target container (`.mp4`, `.mkv`, or `.webm`) without re-encoding or losing a single bit of quality.
2. **No Download Size Limit**:
   - Supports files of any size: 1 GB, 10 GB, 50 GB, 100 GB+ full-length concerts, live stream archives, and 8K multi-hour content.
   - Multi-fragment concurrent streaming with 1 MB chunk buffering and automatic resume capability (`--continue`).
3. **All Available Qualities & Framerates**:
   - **8K Ultra HD** (4320p, 60fps)
   - **4K Ultra HD** (2160p, 60fps)
   - **2K Quad HD** (1440p, 60fps)
   - **Full HD** (1080p, 60fps)
   - **HD** (720p, 60fps)
   - **SD** (480p, 360p, 240p, 144p)
   - Supports HDR10, AV01, VP9, and AVC1 (H.264) video codecs.
4. **All Audio Formats & Studio Presets**:
   - **Original Source Stream**: Untouched direct extract (M4A/AAC or Opus) with zero processing.
   - **Lossless WAV**: Uncompressed 16/24-bit PCM audio.
   - **Lossless FLAC**: Bit-perfect studio audio container.
   - **MP3 320 kbps**: Maximum MP3 bitrate (VBR 0 / 320k CBR) with full metadata.
   - **M4A (Apple AAC)**: Native AAC stream without generational loss.
   - **OPUS**: High-efficiency native YouTube stream.
5. **Three Interface Modes**:
   - 🌐 **Modern Web Application** (Dark theme, real-time WebSocket progress, direct browser download option).
   - 💻 **Native Windows Desktop GUI** (PyQt6 native interface with Windows Explorer folder integration).
   - ⚡ **Command-Line Interface (CLI)** (Interactive terminal wizard or direct flags).

---

## 📦 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/abhishek-3917/youtube_video_downloader.git
   cd youtube_video_downloader
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **FFmpeg requirement:**
   - Make sure `ffmpeg` is installed and available in your system `PATH`.
   - On Windows, you can install via winget:
     ```bash
     winget install Gyan.FFmpeg
     ```
   - On macOS:
     ```bash
     brew install ffmpeg
     ```
   - On Linux (Ubuntu/Debian):
     ```bash
     sudo apt update && sudo apt install ffmpeg
     ```

---

## 🚀 Quick Start (Zero-Terminal Launchers)

### 💻 Native Desktop GUI (No Terminal Window)
Simply double-click either:
* **`Launch_GUI.vbs`** (Opens the GUI window silently with **zero terminal**)
* **`gui.pyw`** (Windows pure GUI script)
* **`start_gui.bat`** (Launches silently in the background)

### 🌐 Web Interface (No Terminal Window)
Double-click:
* **`Launch_Web.vbs`** (Silently starts the backend server and opens your browser to http://127.0.0.1:8000)
* **`start_web.bat`**

### ⚡ Command-Line Interface (CLI) (Only if terminal is desired)
```bash
# Interactive wizard:
python cli.py -i

# Download highest resolution available:
python cli.py "https://www.youtube.com/watch?v=..."

# Download in 4K (2160p) in MKV:
python cli.py "https://www.youtube.com/watch?v=..." -q 2160 -c mkv

# Download Lossless WAV audio only:
python cli.py "https://www.youtube.com/watch?v=..." -a --audio-format wav

# Download 320kbps MP3 audio only:
python cli.py "https://www.youtube.com/watch?v=..." -a --audio-format mp3

# List all available stream itags and codecs:
python cli.py "https://www.youtube.com/watch?v=..." -l
```

---

## 📁 Project Architecture

- `core_downloader.py` — Core extraction & download engine. Configures `yt-dlp` and `ffmpeg` with no-compression flags, JS challenge solver (Node.js runtime), and chunked streaming.
- `app.py` — FastAPI server handling REST endpoints and real-time WebSocket progress broadcasts.
- `static/` — Frontend UI assets:
  - `index.html` — Sleek, responsive layout with glassmorphic cards and live badges.
  - `style.css` — Studio dark theme with neon cyan & indigo accents.
  - `app.js` — WebSocket client, dynamic format tables, and player launcher.
- `gui.py` — PyQt6 native desktop window for Windows.
- `cli.py` — Terminal client with real-time ASCII progress bar.
- `downloads/` — Default directory where lossless media files are saved.

---

## 🍪 Bypassing YouTube "Sign in to confirm you're not a bot"

When downloading certain videos, YouTube's automated defenses trigger a bot verification check:
```
ERROR: [youtube] ...: Sign in to confirm you’re not a bot.
```

### How to Bypass in 30 Seconds:
1. In your browser (Chrome, Edge, or Firefox), install the free extension **"Get cookies.txt LOCALLY"** from the Chrome Web Store or Firefox Add-ons.
2. Go to [YouTube.com](https://www.youtube.com) and ensure you are logged in.
3. Click the extension icon in your browser toolbar and click **Export**.
4. In the Downloader app:
   - **Web UI**: Open the **"🍪 Cookies & Bot Bypass"** tab and click **Upload & Activate**.
   - **Desktop GUI**: Under **Download Settings**, click **Select cookies.txt...**.
   - **CLI**: Place the file as `cookies.txt` in the app root folder or pass `--cookies cookies.txt`.
5. Re-download your video — it will download immediately at full speed!
