"""
Native Desktop GUI for YouTube Studio Downloader
Built with PyQt6.
Supports:
- All video resolutions (8K, 4K, 1440p, 1080p, 720p, etc.)
- All audio formats (Lossless WAV, Lossless FLAC, MP3 320k, Original source stream, M4A, Opus)
- Zero re-compression (stream copy muxing with ffmpeg)
- No download size limit
- Native Windows directory chooser and Explorer integration
"""

import sys
import os
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QProgressBar, QTabWidget, QFileDialog,
    QMessageBox, QGroupBox, QCheckBox, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QFont

import core_downloader

DARK_STYLESHEET = """
QMainWindow {
    background-color: #0b0e14;
}
QWidget {
    background-color: #0b0e14;
    color: #e2e8f0;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #1e293b;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: bold;
    color: #38bdf8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
}
QLineEdit {
    background-color: #121824;
    border: 1px solid #283548;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f8fafc;
}
QLineEdit:focus {
    border: 1px solid #38bdf8;
}
QPushButton {
    background-color: #4f46e5;
    color: #ffffff;
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 16px;
    border: none;
}
QPushButton:hover {
    background-color: #4338ca;
}
QPushButton:pressed {
    background-color: #3730a3;
}
QPushButton#secondaryBtn {
    background-color: #1e293b;
    color: #cbd5e1;
    border: 1px solid #334155;
}
QPushButton#secondaryBtn:hover {
    background-color: #273549;
}
QPushButton#accentBtn {
    background-color: #0284c7;
}
QPushButton#accentBtn:hover {
    background-color: #0369a1;
}
QPushButton#cancelBtn {
    background-color: #dc2626;
}
QPushButton#cancelBtn:hover {
    background-color: #b91c1c;
}
QTableWidget {
    background-color: #121824;
    border: 1px solid #1e293b;
    border-radius: 6px;
    gridline-color: #1e293b;
}
QTableWidget::item {
    padding: 6px;
}
QHeaderView::section {
    background-color: #1a2234;
    color: #94a3b8;
    padding: 6px;
    border: 1px solid #1e293b;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #1e293b;
    background-color: #121824;
    border-radius: 6px;
}
QTabBar::tab {
    background-color: #0b0e14;
    color: #94a3b8;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background-color: #121824;
    color: #38bdf8;
    font-weight: bold;
    border: 1px solid #1e293b;
    border-bottom: none;
}
QComboBox {
    background-color: #121824;
    border: 1px solid #283548;
    border-radius: 6px;
    padding: 6px 12px;
    color: #f8fafc;
}
QProgressBar {
    border: 1px solid #1e293b;
    border-radius: 6px;
    text-align: center;
    background-color: #121824;
    color: #ffffff;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #06b6d4);
    border-radius: 5px;
}
"""

class InfoWorker(QThread):
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, url: str, cookiefile: str = None, browser: str = None):
        super().__init__()
        self.url = url
        self.cookiefile = cookiefile
        self.browser = browser

    def run(self):
        try:
            info = core_downloader.fetch_video_info(self.url, cookiefile=self.cookiefile, browser=self.browser)
            self.finished_signal.emit(info)
        except Exception as e:
            self.error_signal.emit(str(e))

class DownloadWorker(QThread):
    progress_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, task: core_downloader.DownloadTask):
        super().__init__()
        self.task = task

    def run(self):
        def on_progress(data: dict):
            self.progress_signal.emit(data)

        try:
            core_downloader.execute_download(self.task, on_progress)
            if self.task.status == "finished":
                self.finished_signal.emit(self.task.to_dict())
            elif self.task.status in ["error", "cancelled"]:
                self.error_signal.emit(self.task.error_message or "Download cancelled.")
        except Exception as e:
            self.error_signal.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Studio Downloader PRO (Zero Compression)")
        self.resize(960, 720)
        self.setStyleSheet(DARK_STYLESHEET)

        self.current_info = None
        self.current_task = None
        self.active_download_worker = None
        self.download_dir = core_downloader.DEFAULT_DOWNLOAD_DIR
        self.last_downloaded_file = None

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Header Title
        title_label = QLabel("YouTube Studio Downloader PRO")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #f8fafc;")
        subtitle_label = QLabel("Bit-for-bit lossless muxing • Zero compression • No file size limit")
        subtitle_label.setStyleSheet("font-size: 12px; color: #38bdf8;")
        main_layout.addWidget(title_label)
        main_layout.addWidget(subtitle_label)

        # URL Input Bar
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter or paste YouTube video URL here...")
        self.url_input.returnPressed.connect(self.fetch_info)

        paste_btn = QPushButton("Paste")
        paste_btn.setObjectName("secondaryBtn")
        paste_btn.clicked.connect(self.paste_url)

        self.inspect_btn = QPushButton("Inspect Formats")
        self.inspect_btn.clicked.connect(self.fetch_info)

        url_layout.addWidget(self.url_input, stretch=7)
        url_layout.addWidget(paste_btn, stretch=1)
        url_layout.addWidget(self.inspect_btn, stretch=2)
        main_layout.addLayout(url_layout)

        # Video Info Summary Banner
        self.info_group = QGroupBox("Video Metadata")
        info_layout = QVBoxLayout(self.info_group)
        self.video_title_lbl = QLabel("No video loaded yet.")
        self.video_title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #f1f5f9;")
        self.video_sub_lbl = QLabel("")
        self.video_sub_lbl.setStyleSheet("color: #94a3b8;")

        # Quick action buttons
        quick_layout = QHBoxLayout()
        self.quick_best_btn = QPushButton("⭐ Download Best Video (Max Quality) + Audio")
        self.quick_best_btn.setObjectName("accentBtn")
        self.quick_best_btn.clicked.connect(self.download_best_video)
        self.quick_best_btn.setEnabled(False)

        self.quick_audio_btn = QPushButton("🎵 Download Best Untouched Audio")
        self.quick_audio_btn.setObjectName("secondaryBtn")
        self.quick_audio_btn.clicked.connect(self.download_best_audio)
        self.quick_audio_btn.setEnabled(False)

        quick_layout.addWidget(self.quick_best_btn)
        quick_layout.addWidget(self.quick_audio_btn)

        info_layout.addWidget(self.video_title_lbl)
        info_layout.addWidget(self.video_sub_lbl)
        info_layout.addLayout(quick_layout)
        main_layout.addWidget(self.info_group)

        # Tabs for Streams
        self.tab_widget = QTabWidget()

        # Tab 1: Video Streams
        tab_video = QWidget()
        tab_video_layout = QVBoxLayout(tab_video)
        
        container_ctrl_layout = QHBoxLayout()
        container_ctrl_layout.addWidget(QLabel("Target Container:"))
        self.container_combo = QComboBox()
        self.container_combo.addItems(["MP4 (Stream-copy)", "MKV (Lossless Matroska)", "WebM"])
        container_ctrl_layout.addWidget(self.container_combo)
        container_ctrl_layout.addStretch()

        self.video_table = QTableWidget(0, 5)
        self.video_table.setHorizontalHeaderLabels(["Resolution", "Framerate", "Codec", "Est. Total Size", "Download"])
        self.video_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.video_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.video_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        tab_video_layout.addLayout(container_ctrl_layout)
        tab_video_layout.addWidget(self.video_table)
        self.tab_widget.addTab(tab_video, "Video Streams (All Qualities)")

        # Tab 2: Audio Formats
        tab_audio = QWidget()
        tab_audio_layout = QVBoxLayout(tab_audio)

        self.audio_table = QTableWidget(0, 4)
        self.audio_table.setHorizontalHeaderLabels(["Format / Preset", "Type", "Description", "Download"])
        self.audio_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.audio_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.audio_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        tab_audio_layout.addWidget(self.audio_table)
        self.tab_widget.addTab(tab_audio, "Audio Formats (WAV / FLAC / MP3 / M4A / OPUS)")

        # Tab 3: Options / Settings
        tab_settings = QWidget()
        tab_settings_layout = QVBoxLayout(tab_settings)

        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Download Directory:"))
        self.dir_input = QLineEdit(self.download_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.clicked.connect(self.browse_folder)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(browse_btn)

        cookie_layout = QHBoxLayout()
        cookie_layout.addWidget(QLabel("Cookies File (Bypass Bot Check):"))
        default_cookie = core_downloader.DEFAULT_COOKIE_FILE if os.path.exists(core_downloader.DEFAULT_COOKIE_FILE) else ""
        self.cookie_input = QLineEdit(default_cookie)
        self.cookie_input.setPlaceholderText("Select cookies.txt to bypass YouTube bot detection")
        browse_cookie_btn = QPushButton("Select cookies.txt...")
        browse_cookie_btn.setObjectName("secondaryBtn")
        browse_cookie_btn.clicked.connect(self.browse_cookies)
        cookie_layout.addWidget(self.cookie_input)
        cookie_layout.addWidget(browse_cookie_btn)

        browser_layout = QHBoxLayout()
        browser_layout.addWidget(QLabel("Or Read Cookies from Browser:"))
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["None", "Chrome", "Edge", "Firefox", "Brave"])
        browser_layout.addWidget(self.browser_combo)
        browser_layout.addStretch()

        self.embed_thumb_cb = QCheckBox("Embed Video Thumbnail / Cover Art")
        self.embed_sub_cb = QCheckBox("Embed English Subtitles (if available)")

        tab_settings_layout.addLayout(dir_layout)
        tab_settings_layout.addLayout(cookie_layout)
        tab_settings_layout.addLayout(browser_layout)
        tab_settings_layout.addWidget(self.embed_thumb_cb)
        tab_settings_layout.addWidget(self.embed_sub_cb)
        tab_settings_layout.addStretch()
        self.tab_widget.addTab(tab_settings, "Download Settings")

        main_layout.addWidget(self.tab_widget)

        # Progress Section
        self.progress_group = QGroupBox("Download Progress")
        progress_layout = QVBoxLayout(self.progress_group)

        self.status_lbl = QLabel("Ready.")
        self.status_lbl.setStyleSheet("color: #38bdf8; font-weight: 600;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        metrics_layout = QHBoxLayout()
        self.speed_lbl = QLabel("Speed: --")
        self.size_lbl = QLabel("Downloaded: --")
        self.eta_lbl = QLabel("ETA: --")
        metrics_layout.addWidget(self.speed_lbl)
        metrics_layout.addWidget(self.size_lbl)
        metrics_layout.addWidget(self.eta_lbl)

        # Actions on completion
        self.actions_layout = QHBoxLayout()
        self.open_file_btn = QPushButton("▶ Open Downloaded File")
        self.open_file_btn.setObjectName("accentBtn")
        self.open_file_btn.setEnabled(False)
        self.open_file_btn.clicked.connect(self.open_downloaded_file)

        self.open_folder_btn = QPushButton("📁 Show in Windows Explorer")
        self.open_folder_btn.setObjectName("secondaryBtn")
        self.open_folder_btn.clicked.connect(self.open_download_folder)

        self.cancel_btn = QPushButton("✕ Cancel Download")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_download)

        self.actions_layout.addWidget(self.open_file_btn)
        self.actions_layout.addWidget(self.open_folder_btn)
        self.actions_layout.addWidget(self.cancel_btn)

        progress_layout.addWidget(self.status_lbl)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addLayout(metrics_layout)
        progress_layout.addLayout(self.actions_layout)
        main_layout.addWidget(self.progress_group)

    def paste_url(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.url_input.setText(text)
            self.fetch_info()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder", self.download_dir)
        if folder:
            self.download_dir = folder
            self.dir_input.setText(folder)

    def browse_cookies(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select cookies.txt", "", "Text Files (*.txt);;All Files (*)")
        if file:
            self.cookie_input.setText(file)

    def fetch_info(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a YouTube video URL.")
            return

        self.inspect_btn.setEnabled(False)
        self.status_lbl.setText("Extracting video formats and streams...")

        cookiefile = self.cookie_input.text().strip() or None
        browser = self.browser_combo.currentText().lower()
        if browser == "none":
            browser = None

        self.info_worker = InfoWorker(url, cookiefile=cookiefile, browser=browser)
        self.info_worker.finished_signal.connect(self.on_info_loaded)
        self.info_worker.error_signal.connect(self.on_info_error)
        self.info_worker.start()

    def on_info_loaded(self, info: dict):
        self.inspect_btn.setEnabled(True)
        self.current_info = info
        self.video_title_lbl.setText(info.get("title", "Untitled"))
        self.video_sub_lbl.setText(
            f"Channel: {info.get('channel')} | Duration: {info.get('formatted_duration')} | Views: {info.get('view_count')}"
        )
        self.quick_best_btn.setEnabled(True)
        self.quick_audio_btn.setEnabled(True)
        self.status_lbl.setText("Formats loaded successfully.")

        # Populate Video Streams Table
        streams = info.get("video_streams", [])
        self.video_table.setRowCount(len(streams))
        for row, s in enumerate(streams):
            self.video_table.setItem(row, 0, QTableWidgetItem(s.get("quality_label", "")))
            self.video_table.setItem(row, 1, QTableWidgetItem(f"{s.get('fps', 30)} fps"))
            self.video_table.setItem(row, 2, QTableWidgetItem(s.get("vcodec", "")))
            self.video_table.setItem(row, 3, QTableWidgetItem(s.get("formatted_size", "")))

            btn = QPushButton("Download")
            btn.clicked.connect(lambda checked, fid=s.get("format_id"), sz=s.get("total_estimated_size", 0): self.download_video_stream(fid, sz))
            self.video_table.setCellWidget(row, 4, btn)

        # Populate Audio Presets Table
        presets = info.get("audio_presets", [])
        self.audio_table.setRowCount(len(presets))
        for row, p in enumerate(presets):
            self.audio_table.setItem(row, 0, QTableWidgetItem(p.get("name", "")))
            self.audio_table.setItem(row, 1, QTableWidgetItem("Lossless" if p.get("lossless") else "High Quality"))
            self.audio_table.setItem(row, 2, QTableWidgetItem(p.get("description", "")))

            btn = QPushButton(f"Download {p.get('ext', '').upper()}")
            btn.clicked.connect(lambda checked, pid=p.get("id"): self.download_audio_preset(pid))
            self.audio_table.setCellWidget(row, 3, btn)

    def on_info_error(self, err_msg: str):
        self.inspect_btn.setEnabled(True)
        self.status_lbl.setText(f"Error: {err_msg}")
        QMessageBox.critical(self, "Error Fetching Video", err_msg)

    def get_selected_container(self) -> str:
        text = self.container_combo.currentText().lower()
        if "mkv" in text:
            return "mkv"
        elif "webm" in text:
            return "webm"
        return "mp4"

    def download_best_video(self):
        if not self.current_info:
            return
        best_stream = self.current_info.get("video_streams", [{}])[0]
        options = {
            "mode": "video",
            "quality": "best",
            "container": self.get_selected_container(),
            "download_dir": self.dir_input.text().strip() or self.download_dir,
            "embed_thumbnail": self.embed_thumb_cb.isChecked(),
            "embed_subtitles": self.embed_sub_cb.isChecked(),
            "expected_size": best_stream.get("total_estimated_size", 0),
        }
        self.start_download(options)

    def download_best_audio(self):
        if not self.current_info:
            return
        best_audio = self.current_info.get("raw_audio_streams", [{}])[0]
        options = {
            "mode": "audio",
            "audio_preset": "best_audio_original",
            "download_dir": self.dir_input.text().strip() or self.download_dir,
            "expected_size": best_audio.get("filesize", 0),
        }
        self.start_download(options)

    def download_video_stream(self, format_id: str, expected_size: int = 0):
        if not self.current_info:
            return
        options = {
            "mode": "video",
            "format_id": format_id,
            "container": self.get_selected_container(),
            "download_dir": self.dir_input.text().strip() or self.download_dir,
            "embed_thumbnail": self.embed_thumb_cb.isChecked(),
            "embed_subtitles": self.embed_sub_cb.isChecked(),
            "expected_size": expected_size,
        }
        self.start_download(options)

    def download_audio_preset(self, preset_id: str):
        if not self.current_info:
            return
        best_audio = self.current_info.get("raw_audio_streams", [{}])[0]
        options = {
            "mode": "audio",
            "audio_preset": preset_id,
            "download_dir": self.dir_input.text().strip() or self.download_dir,
            "expected_size": best_audio.get("filesize", 0),
        }
        self.start_download(options)

    def start_download(self, options: dict):
        url = self.current_info.get("webpage_url") or self.url_input.text().strip()
        options["cookiefile"] = self.cookie_input.text().strip() or None
        browser = self.browser_combo.currentText().lower()
        if browser != "none":
            options["browser"] = browser

        task = core_downloader.DownloadTask("gui-task", url, options)
        self.current_task = task

        self.cancel_btn.setEnabled(True)
        self.open_file_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_lbl.setText("Starting lossless download...")

        self.active_download_worker = DownloadWorker(task)
        self.active_download_worker.progress_signal.connect(self.on_download_progress)
        self.active_download_worker.finished_signal.connect(self.on_download_finished)
        self.active_download_worker.error_signal.connect(self.on_download_error)
        self.active_download_worker.start()

    def on_download_progress(self, data: dict):
        prog = int(data.get("progress", 0))
        self.progress_bar.setValue(prog)
        status = data.get("status", "")
        if status == "downloading":
            self.status_lbl.setText(f"Downloading stream: {data.get('filename')}")
        elif status == "merging":
            self.status_lbl.setText("Muxing video & audio with ffmpeg -c copy (Zero compression)...")
        self.speed_lbl.setText(f"Speed: {data.get('speed', '--')}")
        self.size_lbl.setText(f"Size: {data.get('downloaded_formatted', '--')} / {data.get('total_formatted', '--')}")
        self.eta_lbl.setText(f"ETA: {data.get('eta', '--')}")

    def on_download_finished(self, data: dict):
        self.progress_bar.setValue(100)
        self.status_lbl.setText("✓ Download complete! Lossless stream saved.")
        self.cancel_btn.setEnabled(False)
        self.last_downloaded_file = data.get("filepath")
        if self.last_downloaded_file and os.path.exists(self.last_downloaded_file):
            self.open_file_btn.setEnabled(True)
        QMessageBox.information(self, "Success", f"Download finished successfully!\nSaved to: {self.last_downloaded_file}")

    def on_download_error(self, err_msg: str):
        self.cancel_btn.setEnabled(False)
        self.status_lbl.setText(f"Download stopped: {err_msg}")
        QMessageBox.warning(self, "Download Status", err_msg)

    def cancel_download(self):
        if self.current_task:
            self.current_task.cancel()
            self.status_lbl.setText("Cancelling download...")

    def open_downloaded_file(self):
        f = core_downloader.resolve_filepath(self.last_downloaded_file, self.download_dir) or self.last_downloaded_file
        if f and os.path.exists(f):
            if sys.platform == "win32":
                os.startfile(os.path.normpath(f))

    def open_download_folder(self):
        if self.last_downloaded_file:
            f = core_downloader.resolve_filepath(self.last_downloaded_file, self.download_dir)
            if f and os.path.isfile(f):
                if sys.platform == "win32":
                    subprocess.Popen(f'explorer.exe /select,"{os.path.normpath(f)}"', shell=True)
                return
        folder = self.dir_input.text().strip() or self.download_dir
        if os.path.exists(folder) and sys.platform == "win32":
            os.startfile(os.path.normpath(folder))

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
