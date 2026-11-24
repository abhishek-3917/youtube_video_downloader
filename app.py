"""
FastAPI Server for YouTube Video Downloader
Provides REST API and WebSocket real-time progress updates.
"""

import os
import sys
import io

# Ensure stdout and stderr exist even when running under pythonw.exe (GUI mode without console)
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

import uuid
import asyncio
import subprocess
import mimetypes
import re
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, UploadFile, File, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import core_downloader

app = FastAPI(title="Pro YouTube Downloader", version="2.0.0")

# In-memory store for active and completed download tasks
TASKS: Dict[str, core_downloader.DownloadTask] = {}
ACTIVE_WEBSOCKETS: List[WebSocket] = []

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(core_downloader.DEFAULT_DOWNLOAD_DIR, exist_ok=True)

# Mount static folder
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

class URLRequest(BaseModel):
    url: str
    browser: Optional[str] = None
    cookiefile: Optional[str] = None

class DownloadRequest(BaseModel):
    url: str
    mode: str = "video"  # 'video', 'audio', 'custom'
    quality: Optional[str] = "best"
    format_id: Optional[str] = None
    container: str = "mp4"
    audio_preset: str = "best_audio_original"
    embed_thumbnail: bool = False
    embed_subtitles: bool = False
    download_dir: Optional[str] = None
    expected_size: Optional[int] = None
    browser: Optional[str] = None
    cookiefile: Optional[str] = None

class ActionRequest(BaseModel):
    path: str

async def broadcast_task_update(task_data: Dict[str, Any]):
    """Broadcast real-time task update to all connected WebSocket clients."""
    if not ACTIVE_WEBSOCKETS:
        return
    disconnected = []
    for ws in ACTIVE_WEBSOCKETS:
        try:
            await ws.send_json({"type": "progress", "data": task_data})
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in ACTIVE_WEBSOCKETS:
            ACTIVE_WEBSOCKETS.remove(ws)

def run_download_in_thread(task: core_downloader.DownloadTask, loop: asyncio.AbstractEventLoop):
    """Executes the download synchronously in a background worker thread."""
    def on_progress(data: Dict[str, Any]):
        asyncio.run_coroutine_threadsafe(broadcast_task_update(data), loop)

    core_downloader.execute_download(task, on_progress)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>YouTube Downloader UI loading...</h1>")

@app.post("/api/info")
async def get_video_info(req: URLRequest):
    """Fetches video metadata and categorized stream formats."""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty.")
    
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None,
            lambda: core_downloader.fetch_video_info(
                url, cookiefile=req.cookiefile, browser=req.browser
            )
        )
        return {"success": True, "data": info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cookies/status")
async def get_cookie_status():
    """Returns current cookie authentication status."""
    cookie_path = core_downloader.DEFAULT_COOKIE_FILE
    exists = os.path.exists(cookie_path) and os.path.isfile(cookie_path)
    size = os.path.getsize(cookie_path) if exists else 0
    return {
        "has_cookies": exists,
        "path": cookie_path if exists else None,
        "size_bytes": size,
        "size_formatted": core_downloader.format_bytes(size) if exists else "0 B",
        "filename": os.path.basename(cookie_path)
    }

@app.post("/api/cookies/upload")
async def upload_cookie_file(file: UploadFile = File(...)):
    """Uploads a cookies.txt file to authenticate with YouTube and bypass bot checks."""
    try:
        content = await file.read()
        if len(content) < 10:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        
        target_path = core_downloader.DEFAULT_COOKIE_FILE
        with open(target_path, "wb") as f:
            f.write(content)

        return {
            "success": True,
            "message": f"Cookies successfully installed! ({len(content)} bytes)",
            "path": target_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save cookie file: {str(e)}")

@app.delete("/api/cookies")
async def delete_cookie_file():
    """Removes stored cookies.txt file."""
    target_path = core_downloader.DEFAULT_COOKIE_FILE
    if os.path.exists(target_path):
        try:
            os.remove(target_path)
            return {"success": True, "message": "Cookies removed."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "message": "No cookies to remove."}

@app.post("/api/download")
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    """Starts a new download task."""
    task_id = str(uuid.uuid4())[:8]
    options = req.model_dump()
    if not options.get("download_dir"):
        options["download_dir"] = core_downloader.DEFAULT_DOWNLOAD_DIR

    task = core_downloader.DownloadTask(task_id, req.url, options)
    TASKS[task_id] = task

    loop = asyncio.get_event_loop()
    background_tasks.add_task(run_download_in_thread, task, loop)

    return {"success": True, "task_id": task_id, "task": task.to_dict()}

@app.get("/api/tasks")
async def get_all_tasks():
    """Returns list of all active and completed tasks."""
    return {"tasks": [t.to_dict() for t in TASKS.values()]}

@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    """Returns status of a specific task."""
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": TASKS[task_id].to_dict()}

@app.post("/api/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancels a running task."""
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    task = TASKS[task_id]
    task.cancel()
    return {"success": True, "task": task.to_dict()}

def resolve_filepath(path_str: str) -> Optional[str]:
    """Resolves a filepath handling Windows invalid character sanitization (e.g. pipe to fullwidth pipe)."""
    if not path_str:
        return None
    path_str = path_str.strip('"').strip("'")
    norm = os.path.normpath(path_str)
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
    # Search by basename inside default download directory
    base = os.path.basename(path_str)
    for c in [base, base.replace("|", "｜"), base.replace("｜", "|"), base.replace("|", "_")]:
        cand = os.path.join(core_downloader.DEFAULT_DOWNLOAD_DIR, c)
        if os.path.exists(cand):
            return cand
    # Search directory for file containing 11-char YouTube video ID if present
    match = re.search(r'\[([a-zA-Z0-9_-]{11})\]', base)
    if match and os.path.exists(core_downloader.DEFAULT_DOWNLOAD_DIR):
        vid_id = match.group(1)
        for f in os.listdir(core_downloader.DEFAULT_DOWNLOAD_DIR):
            if vid_id in f:
                return os.path.join(core_downloader.DEFAULT_DOWNLOAD_DIR, f)
    return None

def send_bytes_range_requests(file_path: str, request: Request, filename: Optional[str] = None):
    """
    Serves files with full HTTP 206 Partial Content (Byte Range) support.
    Enables instant seeking, header probing (e.g. MP4 moov atom), and in-browser video playback.
    """
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")
    mime, _ = mimetypes.guess_type(file_path)
    if not mime:
        mime = "video/mp4" if file_path.lower().endswith(".mp4") else "application/octet-stream"

    out_name = filename or os.path.basename(file_path)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{out_name}"',
    }

    if range_header:
        try:
            # Parse Range: bytes=start-end
            h_val = range_header.strip().replace("bytes=", "")
            parts = h_val.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1

            if start >= file_size:
                raise HTTPException(status_code=416, detail="Requested range not satisfiable")
            end = min(end, file_size - 1)
            content_length = (end - start) + 1

            def chunk_generator():
                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk_size = min(128 * 1024, remaining)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(content_length)
            return StreamingResponse(
                chunk_generator(),
                status_code=206,
                headers=headers,
                media_type=mime
            )
        except (ValueError, IndexError):
            pass

    # Full content delivery
    headers["Content-Length"] = str(file_size)
    def full_generator():
        with open(file_path, "rb") as f:
            while chunk := f.read(128 * 1024):
                yield chunk

    return StreamingResponse(
        full_generator(),
        status_code=200,
        headers=headers,
        media_type=mime
    )

@app.get("/api/file/{task_id}")
@app.head("/api/file/{task_id}")
async def download_file(task_id: str, request: Request):
    """Streams or serves the downloaded file directly to the user's browser with range seeking."""
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    task = TASKS[task_id]
    resolved = resolve_filepath(task.filepath)
    if task.status != "finished" or not resolved or not os.path.exists(resolved):
        raise HTTPException(status_code=400, detail="File is not ready or does not exist.")
    
    return send_bytes_range_requests(resolved, request, filename=task.filename or os.path.basename(resolved))

@app.get("/api/stream")
@app.head("/api/stream")
async def stream_file(path: str, request: Request):
    """Streams a file by path for in-browser video playback with HTTP 206 Range seeking."""
    resolved = resolve_filepath(path)
    if not resolved or not os.path.exists(resolved):
        raise HTTPException(status_code=404, detail="File does not exist on disk")
    
    return send_bytes_range_requests(resolved, request, filename=os.path.basename(resolved))

@app.post("/api/open-folder")
async def open_download_folder(req: ActionRequest):
    """Opens directory or highlights file in Windows File Explorer."""
    if sys.platform != "win32":
        return {
            "success": False,
            "cloud_mode": True,
            "message": "App is running on a cloud server. Use 'Direct Browser Download' to save files to your computer."
        }

    target = req.path or core_downloader.DEFAULT_DOWNLOAD_DIR
    target = target.strip('"').strip("'")
    resolved = resolve_filepath(target) or target

    try:
        if os.path.isfile(resolved):
            norm = os.path.normpath(resolved)
            # Use explorer /select directly without cmd wrapper
            subprocess.Popen(f'explorer.exe /select,"{norm}"', shell=True)
            return {"success": True, "message": f"Selected file in Explorer: {norm}"}

        folder = resolved if os.path.isdir(resolved) else os.path.dirname(resolved)
        if not os.path.exists(folder):
            folder = core_downloader.DEFAULT_DOWNLOAD_DIR

        if os.path.exists(folder):
            norm = os.path.normpath(folder)
            try:
                os.startfile(norm)
            except Exception:
                subprocess.Popen(f'explorer.exe "{norm}"', shell=True)
            return {"success": True, "message": f"Opened folder: {norm}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open explorer: {str(e)}")

    raise HTTPException(status_code=404, detail="Folder does not exist")

@app.post("/api/open-file")
async def open_downloaded_file(req: ActionRequest):
    """Opens the file in default media player."""
    if sys.platform != "win32":
        return {
            "success": False,
            "cloud_mode": True,
            "message": "App is running on a cloud server. Use 'Play in Browser' or 'Direct Browser Download'."
        }

    target = req.path
    if not target:
        raise HTTPException(status_code=400, detail="No file path provided")
    target = target.strip('"').strip("'")
    resolved = resolve_filepath(target)
    if not resolved or not os.path.exists(resolved):
        raise HTTPException(status_code=404, detail=f"File does not exist: {target}")

    norm = os.path.normpath(resolved)
    try:
        os.startfile(norm)
    except Exception:
        subprocess.Popen(f'cmd.exe /c start "" "{norm}"', shell=True)
    return {"success": True, "message": f"Opened file in player: {norm}"}

@app.get("/api/default-dir")
async def get_default_dir():
    """Returns the default download directory."""
    return {"path": core_downloader.DEFAULT_DOWNLOAD_DIR}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ACTIVE_WEBSOCKETS.append(websocket)
    try:
        while True:
            # Keep socket open and receive any ping/pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        if websocket in ACTIVE_WEBSOCKETS:
            ACTIVE_WEBSOCKETS.remove(websocket)
    except Exception:
        if websocket in ACTIVE_WEBSOCKETS:
            ACTIVE_WEBSOCKETS.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    # Use log_config=None when under pythonw to avoid isatty() NoneType crash
    is_gui_mode = isinstance(sys.stdout, io.StringIO)
    host = os.environ.get("HOST", "127.0.0.1" if is_gui_mode else "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    if is_gui_mode:
        uvicorn.run(app, host=host, port=port, log_config=None)
    else:
        uvicorn.run("app:app", host=host, port=port, reload=False)
