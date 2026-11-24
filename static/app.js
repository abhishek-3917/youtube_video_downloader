/**
 * YouTube Studio Downloader Frontend Script
 * Connects to FastAPI backend and WebSocket for live progress
 */

let currentVideoInfo = null;
let currentTaskId = null;
let currentFilePath = null;
let ws = null;
let defaultDownloadDir = "downloads";

// DOM Elements
const urlInput = document.getElementById('urlInput');
const fetchBtn = document.getElementById('fetchBtn');
const fetchSpinner = document.getElementById('fetchSpinner');
const pasteBtn = document.getElementById('pasteBtn');
const statusMessage = document.getElementById('statusMessage');

// Preview Elements
const videoPreview = document.getElementById('videoPreview');
const videoThumb = document.getElementById('videoThumb');
const videoTitle = document.getElementById('videoTitle');
const videoAuthor = document.getElementById('videoAuthor');
const videoViews = document.getElementById('videoViews');
const videoDate = document.getElementById('videoDate');
const videoDuration = document.getElementById('videoDuration');
const videoDesc = document.getElementById('videoDesc');
const quickBestVideoBtn = document.getElementById('quickBestVideoBtn');
const quickBestAudioBtn = document.getElementById('quickBestAudioBtn');

// Stream Containers
const videoStreamsBody = document.getElementById('videoStreamsBody');
const videoContainerSelect = document.getElementById('videoContainerSelect');
const audioPresetsGrid = document.getElementById('audioPresetsGrid');
const rawAudioBody = document.getElementById('rawAudioBody');

// Advanced
const customDirInput = document.getElementById('customDirInput');
const browseDirBtn = document.getElementById('browseDirBtn');
const embedThumbCheck = document.getElementById('embedThumbCheck');
const embedSubCheck = document.getElementById('embedSubCheck');
const customFormatInput = document.getElementById('customFormatInput');
const downloadCustomBtn = document.getElementById('downloadCustomBtn');

// Progress Elements
const downloadProgressCard = document.getElementById('downloadProgressCard');
const progressFilename = document.getElementById('progressFilename');
const progressStatus = document.getElementById('progressStatus');
const progressBarFill = document.getElementById('progressBarFill');
const metricPercent = document.getElementById('metricPercent');
const metricSpeed = document.getElementById('metricSpeed');
const metricSize = document.getElementById('metricSize');
const metricEta = document.getElementById('metricEta');
const cancelDownloadBtn = document.getElementById('cancelDownloadBtn');
const completionActions = document.getElementById('completionActions');
const playInBrowserBtn = document.getElementById('playInBrowserBtn');
const openFileBtn = document.getElementById('openFileBtn');
const openFolderBtn = document.getElementById('openFolderBtn');
const browserDownloadBtn = document.getElementById('browserDownloadBtn');
const inbrowserPlayerBox = document.getElementById('inbrowserPlayerBox');
const inlineVideoPlayer = document.getElementById('inlineVideoPlayer');
const closePlayerBtn = document.getElementById('closePlayerBtn');
const playerVideoTitle = document.getElementById('playerVideoTitle');

// History
const historyList = document.getElementById('historyList');
const emptyHistory = document.getElementById('emptyHistory');
const openDefaultFolderBtn = document.getElementById('openDefaultFolderBtn');

// Cookies & Auth
const cookieStatusIndicator = document.getElementById('cookieStatusIndicator');
const cookieStatusTitle = document.getElementById('cookieStatusTitle');
const cookieStatusDesc = document.getElementById('cookieStatusDesc');
const deleteCookiesBtn = document.getElementById('deleteCookiesBtn');
const cookieFileInput = document.getElementById('cookieFileInput');
const uploadCookieBtn = document.getElementById('uploadCookieBtn');
const browserCookieSelect = document.getElementById('browserCookieSelect');
const tabCookiesBtn = document.getElementById('tabCookiesBtn');

// Initialize WebSocket
function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('WebSocket connected');
    setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
    }, 25000);
  };

  ws.onmessage = (event) => {
    if (event.data === 'pong') return;
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'progress') {
        handleProgressUpdate(msg.data);
      }
    } catch (e) {
      console.error('Error parsing WS message:', e);
    }
  };

  ws.onclose = () => {
    console.log('WebSocket disconnected, retrying in 3s...');
    setTimeout(connectWebSocket, 3000);
  };
}

// Fetch default directory, cookie status, and saved history on load
async function initApp() {
  connectWebSocket();
  checkCookieStatus();
  loadSavedHistory();
  try {
    const res = await fetch('/api/default-dir');
    const data = await res.json();
    if (data.path) {
      defaultDownloadDir = data.path;
      customDirInput.value = data.path;
    }
  } catch (e) {
    console.error('Failed to get default dir:', e);
  }
}

// Cookie Status & Management
async function checkCookieStatus() {
  try {
    const res = await fetch('/api/cookies/status');
    const data = await res.json();
    if (data.has_cookies) {
      cookieStatusIndicator.className = 'cookie-status-indicator active';
      cookieStatusTitle.textContent = `🟢 Active: ${data.filename} (${data.size_formatted})`;
      cookieStatusDesc.textContent = 'Authenticated with YouTube cookies. Bot detection bypassed!';
      deleteCookiesBtn.classList.remove('hidden');
    } else {
      cookieStatusIndicator.className = 'cookie-status-indicator';
      cookieStatusTitle.textContent = '⚪ Anonymous Mode (No cookies.txt)';
      cookieStatusDesc.textContent = 'Works for most public videos. If blocked by bot-check, upload cookies below.';
      deleteCookiesBtn.classList.add('hidden');
    }
  } catch (e) {
    console.error('Error checking cookie status:', e);
  }
}

uploadCookieBtn.addEventListener('click', async () => {
  const file = cookieFileInput.files[0];
  if (!file) {
    showStatus('Please select a cookies.txt file to upload.', 'error');
    return;
  }
  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/cookies/upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.detail || 'Upload failed');
    }
    showStatus('✓ Cookies installed successfully! You can now download bot-checked videos.', 'info');
    checkCookieStatus();
    cookieFileInput.value = '';
  } catch (e) {
    showStatus(`Failed to upload cookies: ${e.message}`, 'error');
  }
});

deleteCookiesBtn.addEventListener('click', async () => {
  try {
    await fetch('/api/cookies', { method: 'DELETE' });
    showStatus('Cookies file removed.', 'info');
    checkCookieStatus();
  } catch (e) {
    console.error('Failed to remove cookies:', e);
  }
});

// Show Status Messages
function showStatus(text, type = 'info') {
  statusMessage.textContent = text;
  statusMessage.className = `status-msg ${type}`;
  statusMessage.classList.remove('hidden');
}

function clearStatus() {
  statusMessage.classList.add('hidden');
  statusMessage.textContent = '';
}

// Tab Switching
document.querySelectorAll('.tab-btn').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

    button.classList.add('active');
    const tabId = button.getAttribute('data-tab');
    document.getElementById(tabId).classList.add('active');
  });
});

// Clipboard Paste
pasteBtn.addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      urlInput.value = text.trim();
      fetchVideoInfo();
    }
  } catch (err) {
    showStatus('Clipboard permission denied. Please paste manually.', 'error');
  }
});

// URL Fetch Handler
fetchBtn.addEventListener('click', fetchVideoInfo);
urlInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    fetchVideoInfo();
  }
});

async function fetchVideoInfo() {
  const url = urlInput.value.trim();
  if (!url) {
    showStatus('Please enter a YouTube video URL.', 'error');
    return;
  }

  clearStatus();
  fetchSpinner.classList.remove('hidden');
  fetchBtn.disabled = true;

  try {
    const selectedBrowser = browserCookieSelect ? browserCookieSelect.value : 'none';
    const response = await fetch('/api/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, browser: selectedBrowser })
    });

    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.detail || 'Failed to extract video information.');
    }

    currentVideoInfo = data.data;
    renderVideoInfo(currentVideoInfo);
  } catch (error) {
    showStatus(`Error: ${error.message}`, 'error');
    if (error.message.includes('Bot') || error.message.includes('cookies') || error.message.includes('Block') || error.message.includes('player response') || error.message.includes('Verification')) {
      const cookiesTabBtn = document.querySelector('[data-tab="tab-cookies"]');
      if (cookiesTabBtn) cookiesTabBtn.click();
    }
  } finally {
    fetchSpinner.classList.add('hidden');
    fetchBtn.disabled = false;
  }
}

// Render Video Details & Format Lists
function renderVideoInfo(info) {
  videoThumb.src = info.thumbnail || '';
  videoTitle.textContent = info.title || 'Untitled Video';
  videoAuthor.textContent = info.channel || 'Unknown Channel';
  videoViews.textContent = `${info.view_count || '0'} views`;
  videoDate.textContent = info.upload_date ? `Uploaded: ${info.upload_date}` : '';
  videoDuration.textContent = info.formatted_duration || '00:00';
  videoDesc.textContent = info.description || '';

  // 1. Render Video Streams
  videoStreamsBody.innerHTML = '';
  if (info.video_streams && info.video_streams.length > 0) {
    info.video_streams.forEach(stream => {
      const tr = document.createElement('tr');
      const is8k = stream.height >= 4320;
      const is4k = stream.height >= 2160 && stream.height < 4320;

      let badgeClass = 'quality-badge';
      if (is8k) badgeClass += ' badge-8k';
      else if (is4k) badgeClass += ' badge-4k';

      tr.innerHTML = `
        <td>
          <span class="${badgeClass}">${stream.quality_label}</span>
          ${stream.dynamic_range && stream.dynamic_range !== 'SDR' ? `<span class="pill pill-amber" style="margin-left:4px;">${stream.dynamic_range}</span>` : ''}
        </td>
        <td>${stream.fps || 30} fps</td>
        <td><span class="codec-tag">${stream.vcodec || stream.ext}</span></td>
        <td><strong>${stream.formatted_size}</strong></td>
        <td>
          <button class="btn btn-primary btn-sm" onclick="downloadVideoStream('${stream.format_id}', ${stream.total_estimated_size || 0})">
            Download ${stream.quality_label}
          </button>
        </td>
      `;
      videoStreamsBody.appendChild(tr);
    });
  } else {
    videoStreamsBody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:15px; color:var(--text-dim);">No video streams found.</td></tr>`;
  }

  // 2. Render Audio Presets
  audioPresetsGrid.innerHTML = '';
  if (info.audio_presets && info.audio_presets.length > 0) {
    info.audio_presets.forEach(preset => {
      const card = document.createElement('div');
      card.className = 'audio-preset-card';
      card.innerHTML = `
        <div>
          <div class="audio-card-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>
            ${preset.name}
          </div>
          <p class="audio-card-desc">${preset.description}</p>
        </div>
        <button class="btn btn-secondary btn-sm" onclick="downloadAudioPreset('${preset.id}')">
          Download ${preset.ext.toUpperCase()}
        </button>
      `;
      audioPresetsGrid.appendChild(card);
    });
  }

  // 3. Render Raw Audio Streams
  rawAudioBody.innerHTML = '';
  if (info.raw_audio_streams && info.raw_audio_streams.length > 0) {
    info.raw_audio_streams.forEach(stream => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${stream.ext.toUpperCase()}</strong></td>
        <td><span class="codec-tag">${stream.acodec}</span></td>
        <td>${stream.abr ? stream.abr + ' kbps' : 'Best'}</td>
        <td>${stream.asr ? (stream.asr / 1000) + ' kHz' : '44.1 kHz'}</td>
        <td>${stream.formatted_size}</td>
        <td>
          <button class="btn btn-outline btn-sm" onclick="downloadRawAudio('${stream.format_id}', ${stream.filesize || 0})">
            Direct Raw Extract
          </button>
        </td>
      `;
      rawAudioBody.appendChild(tr);
    });
  }

  videoPreview.classList.remove('hidden');
  videoPreview.scrollIntoView({ behavior: 'smooth' });
}

// Quick Actions
quickBestVideoBtn.addEventListener('click', () => {
  if (!currentVideoInfo) return;
  const bestStream = currentVideoInfo.video_streams && currentVideoInfo.video_streams[0];
  startDownloadRequest({
    url: currentVideoInfo.webpage_url,
    mode: 'video',
    quality: 'best',
    container: videoContainerSelect.value,
    expected_size: bestStream ? bestStream.total_estimated_size : 0
  });
});

quickBestAudioBtn.addEventListener('click', () => {
  if (!currentVideoInfo) return;
  const bestAudio = currentVideoInfo.raw_audio_streams && currentVideoInfo.raw_audio_streams[0];
  startDownloadRequest({
    url: currentVideoInfo.webpage_url,
    mode: 'audio',
    audio_preset: 'best_audio_original',
    expected_size: bestAudio ? bestAudio.filesize : 0
  });
});

function downloadVideoStream(formatId, expectedSize = 0) {
  if (!currentVideoInfo) return;
  startDownloadRequest({
    url: currentVideoInfo.webpage_url,
    mode: 'video',
    format_id: formatId,
    container: videoContainerSelect.value,
    expected_size: expectedSize
  });
}

function downloadAudioPreset(presetId) {
  if (!currentVideoInfo) return;
  const bestAudio = currentVideoInfo.raw_audio_streams && currentVideoInfo.raw_audio_streams[0];
  startDownloadRequest({
    url: currentVideoInfo.webpage_url,
    mode: 'audio',
    audio_preset: presetId,
    expected_size: bestAudio ? bestAudio.filesize : 0
  });
}

function downloadRawAudio(formatId, expectedSize = 0) {
  if (!currentVideoInfo) return;
  startDownloadRequest({
    url: currentVideoInfo.webpage_url,
    mode: 'custom',
    format_id: formatId,
    expected_size: expectedSize
  });
}

downloadCustomBtn.addEventListener('click', () => {
  const customFormat = customFormatInput.value.trim();
  if (!customFormat || !currentVideoInfo) return;
  startDownloadRequest({
    url: currentVideoInfo.webpage_url,
    mode: 'custom',
    format_id: customFormat,
    container: videoContainerSelect.value
  });
});

browseDirBtn.addEventListener('click', () => {
  customDirInput.value = defaultDownloadDir;
});

// Trigger Download Request to Backend
async function startDownloadRequest(options) {
  options.embed_thumbnail = embedThumbCheck.checked;
  options.embed_subtitles = embedSubCheck.checked;
  options.download_dir = customDirInput.value.trim() || defaultDownloadDir;
  options.browser = browserCookieSelect ? browserCookieSelect.value : 'none';

  showStatus('Dispatching download task to engine...', 'info');

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options)
    });

    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.detail || 'Could not start download');
    }

    currentTaskId = data.task_id;
    setupProgressUI(data.task);
  } catch (err) {
    showStatus(`Failed to initiate download: ${err.message}`, 'error');
  }
}

// Progress UI Setup
function setupProgressUI(task) {
  downloadProgressCard.classList.remove('hidden');
  completionActions.classList.add('hidden');
  cancelDownloadBtn.classList.remove('hidden');

  progressFilename.textContent = task.filename || currentVideoInfo.title || 'Downloading...';
  progressStatus.textContent = 'Starting multi-threaded stream download (Zero Compression)...';
  progressBarFill.style.width = '0%';
  metricPercent.textContent = '0%';
  metricSpeed.textContent = 'Connecting...';
  metricSize.textContent = 'Calculating...';
  metricEta.textContent = '--:--';

  downloadProgressCard.scrollIntoView({ behavior: 'smooth' });
}

// Handle WebSocket Progress Updates
function handleProgressUpdate(task) {
  if (task.task_id !== currentTaskId) return;

  if (task.filename) {
    progressFilename.textContent = task.filename;
  }

  if (task.status === 'downloading') {
    progressStatus.textContent = 'Downloading stream (Direct chunked stream copy)...';
    progressBarFill.style.width = `${task.progress}%`;
    metricPercent.textContent = `${task.progress}%`;
    metricSpeed.textContent = task.speed;
    metricSize.textContent = `${task.downloaded_formatted} / ${task.total_formatted}`;
    metricEta.textContent = task.eta;
  } else if (task.status === 'merging') {
    progressStatus.textContent = 'Muxing video & audio with ffmpeg stream-copy (Zero Re-compression)...';
    progressBarFill.style.width = '100%';
    metricPercent.textContent = '100%';
    metricSpeed.textContent = 'Muxing';
    metricEta.textContent = 'Finalizing';
  } else if (task.status === 'finished') {
    progressStatus.textContent = '✓ Completed! Lossless file saved to disk.';
    progressBarFill.style.width = '100%';
    metricPercent.textContent = '100%';
    metricSpeed.textContent = 'Saved';
    metricEta.textContent = '00:00';
    currentFilePath = task.filepath;

    cancelDownloadBtn.classList.add('hidden');
    completionActions.classList.remove('hidden');
    browserDownloadBtn.href = `/api/file/${task.task_id}`;

    addHistoryItem(task);
  } else if (task.status === 'error') {
    progressStatus.textContent = `❌ Error: ${task.error_message}`;
    cancelDownloadBtn.classList.add('hidden');
  } else if (task.status === 'cancelled') {
    progressStatus.textContent = 'Download was cancelled.';
    cancelDownloadBtn.classList.add('hidden');
  }
}

// Cancel Download
cancelDownloadBtn.addEventListener('click', async () => {
  if (!currentTaskId) return;
  try {
    await fetch(`/api/task/${currentTaskId}/cancel`, { method: 'POST' });
  } catch (e) {
    console.error('Cancel failed:', e);
  }
});

// In-Browser Video Player
function playVideoInBrowser(videoSrc, title) {
  if (!videoSrc) return;
  if (!inlineVideoPlayer || !inbrowserPlayerBox) return;

  inlineVideoPlayer.pause();
  inlineVideoPlayer.src = videoSrc;
  if (playerVideoTitle && title) {
    playerVideoTitle.textContent = title;
  }
  inbrowserPlayerBox.classList.remove('hidden');
  inlineVideoPlayer.play().catch(err => {
    console.log('Autoplay deferred by browser policy:', err);
  });
  inbrowserPlayerBox.scrollIntoView({ behavior: 'smooth' });
}

if (playInBrowserBtn) {
  playInBrowserBtn.addEventListener('click', () => {
    const path = currentFilePath || localStorage.getItem('last_download_path');
    const title = progressFilename ? progressFilename.textContent : 'Downloaded Video';
    if (currentTaskId) {
      playVideoInBrowser(`/api/file/${currentTaskId}`, title);
    } else if (path) {
      playVideoInBrowser(`/api/stream?path=${encodeURIComponent(path)}`, title);
    } else {
      showStatus('No downloaded video available to play.', 'error');
    }
  });
}

if (closePlayerBtn) {
  closePlayerBtn.addEventListener('click', () => {
    if (inlineVideoPlayer) {
      inlineVideoPlayer.pause();
      inlineVideoPlayer.src = '';
    }
    if (inbrowserPlayerBox) {
      inbrowserPlayerBox.classList.add('hidden');
    }
  });
}

// File and Folder Actions
openFileBtn.addEventListener('click', async () => {
  const path = currentFilePath || localStorage.getItem('last_download_path');
  if (!path) {
    showStatus('No downloaded file found to open. Please download a video first.', 'error');
    return;
  }
  showStatus('Opening media file in your default player...', 'info');
  try {
    const res = await fetch('/api/open-file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      showStatus('Failed to open file: ' + (data.detail || 'File not found on disk'), 'error');
    } else {
      showStatus('✓ Media file opened in player!', 'info');
    }
  } catch (e) {
    showStatus('Failed to open file: ' + e.message, 'error');
  }
});

openFolderBtn.addEventListener('click', async () => {
  const path = currentFilePath || localStorage.getItem('last_download_path') || defaultDownloadDir;
  showStatus('Opening in File Explorer...', 'info');
  try {
    const res = await fetch('/api/open-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      showStatus('Failed to open folder: ' + (data.detail || 'Folder not found'), 'error');
    } else {
      showStatus('✓ Opened in File Explorer!', 'info');
    }
  } catch (e) {
    showStatus('Failed to open folder: ' + e.message, 'error');
  }
});

openDefaultFolderBtn.addEventListener('click', async () => {
  showStatus('Opening Downloads folder...', 'info');
  try {
    const res = await fetch('/api/open-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: defaultDownloadDir })
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      showStatus('Failed to open downloads folder: ' + (data.detail || 'Folder not found'), 'error');
    } else {
      showStatus('✓ Opened Downloads folder!', 'info');
    }
  } catch (e) {
    showStatus('Failed to open folder: ' + e.message, 'error');
  }
});

// Download History Persistence & Management
function getSavedHistory() {
  try {
    return JSON.parse(localStorage.getItem('saved_download_history') || '[]');
  } catch {
    return [];
  }
}

function saveTaskToStorage(task) {
  try {
    const history = getSavedHistory().filter(item => item.filepath !== task.filepath);
    history.unshift({
      task_id: task.task_id,
      filename: task.filename,
      filepath: task.filepath,
      total_formatted: task.total_formatted || 'Downloaded'
    });
    localStorage.setItem('saved_download_history', JSON.stringify(history.slice(0, 25)));
  } catch (e) {
    console.error('Failed to save history to storage:', e);
  }
}

function loadSavedHistory() {
  const history = getSavedHistory();
  if (!history || history.length === 0) return;
  if (emptyHistory) emptyHistory.style.display = 'none';

  history.forEach(item => {
    appendHistoryCard(item);
  });
}

function appendHistoryCard(item) {
  const el = document.createElement('div');
  el.className = 'history-item';
  const encodedPath = encodeURIComponent(item.filepath);
  const encodedName = encodeURIComponent(item.filename);
  const playUrl = item.task_id ? `/api/file/${item.task_id}` : `/api/stream?path=${encodedPath}`;

  el.innerHTML = `
    <div class="history-item-info">
      <div class="history-filename">${item.filename}</div>
      <div class="history-meta">${item.total_formatted || ''} • Saved to: ${item.filepath}</div>
    </div>
    <div style="display: flex; gap: 6px; flex-wrap: wrap;">
      <button class="btn btn-accent btn-sm" onclick="playInBrowserStream('${encodedPath}', '${encodedName}')">Watch</button>
      <button class="btn btn-primary btn-sm" onclick="openSpecificFile('${encodedPath}')">Play in App</button>
      <button class="btn btn-secondary btn-sm" onclick="openSpecificFolder('${encodedPath}')">Show in Folder</button>
      <a class="btn btn-outline btn-sm" href="${playUrl}" download>Save to Browser</a>
    </div>
  `;
  historyList.appendChild(el);
}

// Add Item to History
function addHistoryItem(task) {
  if (emptyHistory) {
    emptyHistory.style.display = 'none';
  }

  currentFilePath = task.filepath;
  localStorage.setItem('last_download_path', task.filepath);
  if (task.task_id) {
    localStorage.setItem('last_download_task_id', task.task_id);
  }
  saveTaskToStorage(task);

  const item = document.createElement('div');
  item.className = 'history-item';
  const encodedPath = encodeURIComponent(task.filepath);
  const encodedName = encodeURIComponent(task.filename);
  const playUrl = task.task_id ? `/api/file/${task.task_id}` : `/api/stream?path=${encodedPath}`;

  item.innerHTML = `
    <div class="history-item-info">
      <div class="history-filename">${task.filename}</div>
      <div class="history-meta">${task.total_formatted} • Saved to: ${task.filepath}</div>
    </div>
    <div style="display: flex; gap: 6px; flex-wrap: wrap;">
      <button class="btn btn-accent btn-sm" onclick="playInBrowserStream('${encodedPath}', '${encodedName}')">Watch</button>
      <button class="btn btn-primary btn-sm" onclick="openSpecificFile('${encodedPath}')">Play in App</button>
      <button class="btn btn-secondary btn-sm" onclick="openSpecificFolder('${encodedPath}')">Show in Folder</button>
      <a class="btn btn-outline btn-sm" href="${playUrl}" download>Save to Browser</a>
    </div>
  `;
  historyList.prepend(item);
}

window.playInBrowserStream = function(encodedPath, encodedName) {
  const path = decodeURIComponent(encodedPath);
  const name = decodeURIComponent(encodedName);
  playVideoInBrowser(`/api/stream?path=${encodeURIComponent(path)}`, name);
};

window.openSpecificFile = async function(encodedPath) {
  const path = decodeURIComponent(encodedPath);
  showStatus('Opening in default media player...', 'info');
  try {
    const res = await fetch('/api/open-file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      showStatus('Failed to open file: ' + (data.detail || 'File not found'), 'error');
    } else {
      showStatus('✓ Media file opened in player!', 'info');
    }
  } catch (e) {
    showStatus('Failed to open file: ' + e.message, 'error');
  }
};

window.openSpecificFolder = async function(encodedPath) {
  const path = decodeURIComponent(encodedPath);
  showStatus('Locating file in File Explorer...', 'info');
  try {
    const res = await fetch('/api/open-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      showStatus('Failed to open in Explorer: ' + (data.detail || 'Folder not found'), 'error');
    } else {
      showStatus('✓ Highlighted file in File Explorer!', 'info');
    }
  } catch (e) {
    showStatus('Failed to open Explorer: ' + e.message, 'error');
  }
};

// Start
window.addEventListener('DOMContentLoaded', initApp);
