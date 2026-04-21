#!/usr/bin/env python3
"""Voice Dump Pipeline — record on phone, transcribe on Pi."""

import os
import time
from datetime import datetime
from pathlib import Path

import subprocess
from flask import Flask, request, jsonify, render_template_string, send_file
from faster_whisper import WhisperModel

APP_DIR = Path(__file__).parent
UPLOAD_DIR = APP_DIR / "uploads"
TRANSCRIPT_DIR = APP_DIR / "transcripts"
PROMO_DIR = Path("/home/shanebrain/you-probably-think-this-book-is-about-you/promo")
BOOK_DIR = Path("/home/shanebrain/you-probably-think-this-book-is-about-you")
V1_SCENES = BOOK_DIR / "scenes" / "drafts"
V1_INTERLUDES = BOOK_DIR / "scenes" / "interludes"
V1_COMPILED = BOOK_DIR / "compiled"
V1_AUDIO_SCRIPT = BOOK_DIR / "AUDIO-SCRIPT-MASTER.md"
V2_TRACKS = BOOK_DIR / "volume-two" / "tracks" / "drafts"
V2_INTERLUDES = BOOK_DIR / "volume-two" / "tracks" / "interludes"
UPLOAD_DIR.mkdir(exist_ok=True)
TRANSCRIPT_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max

# Load model on first request (lazy)
_model = None

def get_model():
    global _model
    if _model is None:
        print("Loading Whisper model (small)... this takes ~60s first time")
        _model = WhisperModel("small", device="cpu", compute_type="int8")
        print("Model loaded.")
    return _model

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Voice Dump</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, system-ui, sans-serif;
    background: #0a0a0a;
    color: #e0e0e0;
    min-height: 100vh;
    padding: 20px;
}
.container { max-width: 600px; margin: 0 auto; }
h1 {
    font-size: 1.5rem;
    color: #fff;
    margin-bottom: 8px;
}
.subtitle {
    color: #888;
    font-size: 0.9rem;
    margin-bottom: 30px;
}
.upload-zone {
    border: 2px dashed #333;
    border-radius: 12px;
    padding: 40px 20px;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s;
    margin-bottom: 20px;
}
.upload-zone:hover, .upload-zone.dragover {
    border-color: #666;
}
.upload-zone input { display: none; }
.upload-btn {
    background: #fff;
    color: #000;
    border: none;
    padding: 14px 32px;
    border-radius: 8px;
    font-size: 1.1rem;
    font-weight: 600;
    cursor: pointer;
    display: inline-block;
    margin-top: 12px;
}
.upload-btn:disabled {
    background: #444;
    color: #888;
    cursor: not-allowed;
}
.status {
    text-align: center;
    padding: 16px;
    font-size: 0.95rem;
    color: #aaa;
    display: none;
}
.status.show { display: block; }
.spinner {
    display: inline-block;
    width: 20px; height: 20px;
    border: 2px solid #444;
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-right: 8px;
    vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }
.transcript-box {
    background: #111;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 20px;
    margin-top: 20px;
    white-space: pre-wrap;
    font-family: 'Georgia', serif;
    font-size: 0.95rem;
    line-height: 1.6;
    color: #ddd;
    max-height: 60vh;
    overflow-y: auto;
    display: none;
}
.transcript-box.show { display: block; }
.meta {
    color: #666;
    font-size: 0.8rem;
    margin-top: 12px;
    text-align: center;
}
.copy-btn {
    background: #222;
    color: #aaa;
    border: 1px solid #444;
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 0.9rem;
    cursor: pointer;
    margin-top: 12px;
    display: none;
}
.copy-btn.show { display: inline-block; }
.copy-btn:active { background: #333; }
.history { margin-top: 40px; }
.history h2 {
    font-size: 1.1rem;
    color: #888;
    margin-bottom: 12px;
}
.history-item {
    background: #111;
    border: 1px solid #222;
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 8px;
    cursor: pointer;
}
.history-item:hover { border-color: #444; }
.history-item .name { color: #ccc; font-size: 0.9rem; }
.history-item .date { color: #666; font-size: 0.75rem; }
.record-section {
    text-align: center;
    margin-bottom: 24px;
}
.record-btn {
    width: 80px; height: 80px;
    border-radius: 50%;
    background: #cc0000;
    border: 4px solid #fff;
    cursor: pointer;
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
}
.record-btn.paused {
    border-color: #f0a500;
}
.record-btn.paused .inner {
    background: #f0a500;
    animation: none;
}
.record-btn.recording {
    background: #ff0000;
    animation: pulse 1s infinite;
}
.record-btn .inner {
    width: 30px; height: 30px;
    background: #fff;
    border-radius: 50%;
    transition: all 0.2s;
}
.record-btn.recording .inner {
    width: 24px; height: 24px;
    border-radius: 4px;
}
@keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(255,0,0,0.4); }
    50% { box-shadow: 0 0 0 20px rgba(255,0,0,0); }
}
.record-label {
    color: #888;
    font-size: 0.85rem;
    margin-top: 10px;
}
.or-divider {
    color: #444;
    text-align: center;
    margin: 16px 0;
    font-size: 0.85rem;
}
.tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 24px;
}
.tab {
    flex: 1;
    padding: 12px;
    border: 1px solid #333;
    border-radius: 8px;
    background: #111;
    color: #888;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
}
.tab.active {
    background: #fff;
    color: #000;
    border-color: #fff;
}
.script-list { display: flex; flex-direction: column; gap: 8px; }
.script-item {
    background: #111;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 16px;
    cursor: pointer;
}
.script-item:hover { border-color: #666; }
.script-item .title { color: #fff; font-size: 1rem; font-weight: 600; }
.script-item .desc { color: #888; font-size: 0.8rem; margin-top: 4px; }
.script-back {
    color: #888;
    font-size: 0.9rem;
    cursor: pointer;
    margin-bottom: 16px;
}
.script-back:hover { color: #fff; }
.script-content {
    background: #111;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 20px;
    white-space: pre-wrap;
    font-family: 'Georgia', serif;
    font-size: 1.05rem;
    line-height: 1.8;
    color: #e0e0e0;
    max-height: 70vh;
    overflow-y: auto;
}
.script-viewer { margin-top: 8px; }
.playback-section {
    background: #111;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 16px;
    margin-top: 16px;
    display: none;
}
.playback-section.show { display: block; }
.playback-section h3 {
    color: #fff;
    font-size: 0.95rem;
    margin-bottom: 12px;
}
.playback-section audio {
    width: 100%;
    margin-bottom: 12px;
}
.speed-controls {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 12px;
}
.speed-controls label {
    color: #aaa;
    font-size: 0.85rem;
}
.speed-controls input[type=range] {
    flex: 1;
    min-width: 120px;
    accent-color: #fff;
}
.speed-val {
    color: #fff;
    font-weight: 600;
    min-width: 40px;
}
.speed-presets {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-bottom: 12px;
}
.speed-presets button {
    background: #222;
    color: #aaa;
    border: 1px solid #444;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 0.8rem;
    cursor: pointer;
}
.speed-presets button:hover { background: #333; }
.speed-presets button.active { background: #fff; color: #000; border-color: #fff; }
.export-btn {
    background: #1a6b1a;
    color: #fff;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 0.9rem;
    cursor: pointer;
    margin-top: 4px;
}
.export-btn:hover { background: #228b22; }
.export-btn:disabled { background: #333; color: #666; cursor: not-allowed; }
.export-status {
    color: #888;
    font-size: 0.8rem;
    margin-top: 8px;
}
</style>
</head>
<body>
<div class="container">
    <div class="tabs">
        <button class="tab active" onclick="showTab('record')">Record</button>
        <button class="tab" onclick="showTab('book')">Book</button>
        <button class="tab" onclick="showTab('scripts')">Promo</button>
    </div>

    <div id="recordTab">
    <h1>Voice Dump</h1>
    <p class="subtitle">Record or upload. Whisper transcribes. The grit stays in.</p>

    <div class="record-section">
        <div class="record-btn" id="recordBtn" onclick="toggleRecord()">
            <div class="inner"></div>
        </div>
        <div class="record-label" id="recordLabel">Tap to record</div>
    </div>

    <div class="or-divider">— or upload a file —</div>

    <div class="upload-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
        <div>Tap to choose an audio file</div>
        <div style="color:#666; font-size:0.8rem; margin-top:8px">MP3, M4A, WAV, OGG, WEBM</div>
        <input type="file" id="fileInput" accept="audio/*,.mp3,.m4a,.wav,.ogg,.webm,.mp4">
    </div>

    <button class="upload-btn" id="uploadBtn" onclick="upload()" disabled>Transcribe</button>

    <div class="status" id="status"></div>
    <div class="transcript-box" id="transcript"></div>
    <div style="text-align:center">
        <button class="copy-btn" id="copyBtn" onclick="copyTranscript()">Copy transcript</button>
    </div>
    <div class="meta" id="meta"></div>

    <div class="playback-section" id="playbackSection">
        <h3>Playback</h3>
        <audio id="audioPlayer" controls></audio>
        <div class="speed-controls">
            <label>Speed:</label>
            <input type="range" id="speedSlider" min="0.5" max="2.0" step="0.05" value="1.0"
                   oninput="setSpeed(this.value)">
            <span class="speed-val" id="speedVal">1.0x</span>
        </div>
        <div class="speed-presets">
            <button onclick="setSpeed(0.75)">0.75x</button>
            <button onclick="setSpeed(1.0)" class="active">1.0x</button>
            <button onclick="setSpeed(1.15)">1.15x</button>
            <button onclick="setSpeed(1.25)">1.25x</button>
            <button onclick="setSpeed(1.5)">1.5x</button>
            <button onclick="setSpeed(1.75)">1.75x</button>
        </div>
        <button class="export-btn" id="exportBtn" onclick="exportAtSpeed()">Download at this speed</button>
        <div class="export-status" id="exportStatus"></div>
    </div>

    <div class="history" id="historySection">
        <h2>Recent dumps</h2>
        <div id="historyList"></div>
    </div>
    </div><!-- end recordTab -->

    <div id="bookTab" style="display:none">
    <h1>The Book</h1>
    <p class="subtitle">Tap to read. Your reading copy.</p>

    <div class="script-list" id="bookList"></div>

    <div class="script-viewer" id="bookViewer" style="display:none">
        <div class="script-back" onclick="backToBookList()">&larr; Back</div>
        <div class="script-content" id="bookContent"></div>
    </div>
    </div><!-- end bookTab -->

    <div id="scriptsTab" style="display:none">
    <h1>Promo</h1>
    <p class="subtitle">Tap a script to read. Tap copy to grab it.</p>

    <div class="script-list" id="scriptList"></div>

    <div class="script-viewer" id="scriptViewer" style="display:none">
        <div class="script-back" onclick="backToList()">&larr; Back</div>
        <div class="script-content" id="scriptContent"></div>
        <div style="text-align:center; margin-top:16px">
            <button class="copy-btn show" onclick="copyScript()">Copy all</button>
        </div>
    </div>
    </div><!-- end scriptsTab -->
</div>

<script>
let selectedFile = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const status = document.getElementById('status');
const transcript = document.getElementById('transcript');
const copyBtn = document.getElementById('copyBtn');
const meta = document.getElementById('meta');
const recordBtn = document.getElementById('recordBtn');
const recordLabel = document.getElementById('recordLabel');

fileInput.addEventListener('change', (e) => {
    selectedFile = e.target.files[0];
    if (selectedFile) {
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Transcribe: ' + selectedFile.name;
    }
});

let isPaused = false;
let recordingStream = null;
let recordStartTime = null;
let pauseStartTime = null;
let totalPausedMs = 0;

function updateRecordTimer() {
    if (!isRecording) return;
    if (isPaused) {
        recordLabel.textContent = '⏸ PAUSED — tap to resume';
        requestAnimationFrame(updateRecordTimer);
        return;
    }
    const elapsed = Math.floor((Date.now() - recordStartTime - totalPausedMs) / 1000);
    const min = Math.floor(elapsed / 60);
    const sec = String(elapsed % 60).padStart(2, '0');
    recordLabel.textContent = 'Recording ' + min + ':' + sec + ' — tap to stop';
    requestAnimationFrame(updateRecordTimer);
}

async function toggleRecord() {
    if (!isRecording) {
        // START recording
        try {
            recordingStream = await navigator.mediaDevices.getUserMedia({
                audio: { sampleRate: 48000, channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true }
            });
            const options = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? { mimeType: 'audio/webm;codecs=opus' } : {};
            mediaRecorder = new MediaRecorder(recordingStream, options);
            audioChunks = [];
            isPaused = false;
            totalPausedMs = 0;
            mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) audioChunks.push(e.data);
            };
            mediaRecorder.onstop = () => {
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                const now = new Date();
                const name = 'recording-' + now.toISOString().slice(0,19).replace(/[T:]/g,'-') + '.webm';
                selectedFile = new File([blob], name, { type: 'audio/webm' });
                uploadBtn.disabled = false;
                uploadBtn.textContent = 'Transcribe recording';
                recordingStream.getTracks().forEach(t => t.stop());
                recordingStream = null;
            };
            // Collect chunks every second so nothing is lost on interrupt
            mediaRecorder.start(1000);
            isRecording = true;
            recordStartTime = Date.now();
            recordBtn.classList.add('recording');
            updateRecordTimer();
        } catch(e) {
            alert('Mic access denied. Check your browser settings.');
        }
    } else if (isPaused) {
        // RESUME from pause — restart mic and recorder
        try {
            recordingStream = await navigator.mediaDevices.getUserMedia({
                audio: { sampleRate: 48000, channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true }
            });
            const options = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? { mimeType: 'audio/webm;codecs=opus' } : {};
            mediaRecorder = new MediaRecorder(recordingStream, options);
            mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) audioChunks.push(e.data);
            };
            mediaRecorder.onstop = () => {
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                const now = new Date();
                const name = 'recording-' + now.toISOString().slice(0,19).replace(/[T:]/g,'-') + '.webm';
                selectedFile = new File([blob], name, { type: 'audio/webm' });
                uploadBtn.disabled = false;
                uploadBtn.textContent = 'Transcribe recording';
                recordingStream.getTracks().forEach(t => t.stop());
                recordingStream = null;
            };
            mediaRecorder.start(1000);
            totalPausedMs += Date.now() - pauseStartTime;
            isPaused = false;
            recordBtn.classList.add('recording');
            recordBtn.classList.remove('paused');
        } catch(e) {
            alert('Could not resume mic. Try stopping and starting a new recording.');
        }
    } else {
        // STOP recording
        mediaRecorder.stop();
        isRecording = false;
        isPaused = false;
        recordBtn.classList.remove('recording');
        recordBtn.classList.remove('paused');
        recordLabel.textContent = 'Tap to record';
    }
}

// Auto-pause when phone call / app switch / screen lock
document.addEventListener('visibilitychange', () => {
    if (!isRecording || isPaused) return;
    if (document.hidden) {
        // Page hidden — pause recording, save what we have
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            if (recordingStream) {
                recordingStream.getTracks().forEach(t => t.stop());
                recordingStream = null;
            }
        }
        isPaused = true;
        pauseStartTime = Date.now();
        recordBtn.classList.remove('recording');
        recordBtn.classList.add('paused');
        recordLabel.textContent = '⏸ PAUSED — tap to resume';
    }
});

// Also catch audio interruption directly (iOS)
navigator.mediaDevices.addEventListener('devicechange', () => {
    if (isRecording && !isPaused && mediaRecorder && mediaRecorder.state !== 'recording') {
        isPaused = true;
        pauseStartTime = Date.now();
        recordBtn.classList.remove('recording');
        recordBtn.classList.add('paused');
        recordLabel.textContent = '⏸ PAUSED — tap to resume';
    }
});

async function upload() {
    if (!selectedFile) return;
    const formData = new FormData();
    formData.append('audio', selectedFile);

    uploadBtn.disabled = true;
    status.className = 'status show';
    status.innerHTML = '<span class="spinner"></span> Transcribing... this takes a minute';
    transcript.className = 'transcript-box';
    copyBtn.className = 'copy-btn';
    meta.textContent = '';

    try {
        const resp = await fetch('/transcribe', { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.error) {
            status.innerHTML = 'Error: ' + data.error;
        } else {
            status.className = 'status';
            transcript.textContent = data.text;
            transcript.className = 'transcript-box show';
            copyBtn.className = 'copy-btn show';
            meta.textContent = data.duration + ' · saved to ' + data.filename;
            loadHistory();
        }
    } catch(e) {
        status.innerHTML = 'Error: ' + e.message;
    }
    uploadBtn.disabled = false;
    uploadBtn.textContent = 'Transcribe';
    selectedFile = null;
    fileInput.value = '';
}

function copyTranscript() {
    navigator.clipboard.writeText(transcript.textContent);
    copyBtn.textContent = 'Copied!';
    setTimeout(() => copyBtn.textContent = 'Copy transcript', 2000);
}

async function loadHistory() {
    try {
        const resp = await fetch('/history');
        const data = await resp.json();
        const list = document.getElementById('historyList');
        list.innerHTML = '';
        data.forEach(item => {
            const div = document.createElement('div');
            div.className = 'history-item';
            div.style.display = 'flex';
            div.style.justifyContent = 'space-between';
            div.style.alignItems = 'center';
            const info = document.createElement('div');
            info.innerHTML = '<div class="name">' + item.name + '</div><div class="date">' + item.date + '</div>';
            info.style.flex = '1';
            info.style.cursor = 'pointer';
            info.onclick = async () => {
                const r = await fetch('/transcript/' + encodeURIComponent(item.name));
                const t = await r.text();
                transcript.textContent = t;
                transcript.className = 'transcript-box show';
                copyBtn.className = 'copy-btn show';
            };
            div.appendChild(info);
            if (item.audio) {
                const playBtn = document.createElement('button');
                playBtn.textContent = '\u25B6';
                playBtn.style.cssText = 'background:#222; color:#fff; border:1px solid #444; border-radius:50%; width:36px; height:36px; font-size:1rem; cursor:pointer; flex-shrink:0; margin-left:8px;';
                playBtn.onclick = (e) => { e.stopPropagation(); showPlayer(item.audio); };
                div.appendChild(playBtn);
            }
            list.appendChild(div);
        });
    } catch(e) {}
}

// Drag and drop
const dropZone = document.getElementById('dropZone');
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
        selectedFile = e.dataTransfer.files[0];
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Transcribe: ' + selectedFile.name;
    }
});

let currentAudioFile = null;
const audioPlayer = document.getElementById('audioPlayer');
const speedSlider = document.getElementById('speedSlider');
const speedVal = document.getElementById('speedVal');
const playbackSection = document.getElementById('playbackSection');
const exportBtn = document.getElementById('exportBtn');
const exportStatus = document.getElementById('exportStatus');

function setSpeed(val) {
    val = parseFloat(val);
    audioPlayer.playbackRate = val;
    speedSlider.value = val;
    speedVal.textContent = val.toFixed(2) + 'x';
    document.querySelectorAll('.speed-presets button').forEach(b => {
        b.classList.toggle('active', parseFloat(b.textContent) === val);
    });
    if (currentAudioFile) {
        exportBtn.textContent = 'Download at ' + val.toFixed(2) + 'x speed';
    }
}

function showPlayer(filename) {
    currentAudioFile = filename;
    audioPlayer.src = '/audio/' + encodeURIComponent(filename);
    playbackSection.classList.add('show');
    exportStatus.textContent = '';
    setSpeed(parseFloat(speedSlider.value));
    playbackSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function exportAtSpeed() {
    if (!currentAudioFile) return;
    const speed = parseFloat(speedSlider.value);
    if (speed === 1.0) {
        // Just download the original
        window.location.href = '/audio/' + encodeURIComponent(currentAudioFile);
        return;
    }
    exportBtn.disabled = true;
    exportStatus.textContent = 'Processing... (ffmpeg re-encoding at ' + speed.toFixed(2) + 'x)';
    try {
        const resp = await fetch('/export-speed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file: currentAudioFile, speed: speed }),
        });
        if (!resp.ok) {
            const err = await resp.json();
            exportStatus.textContent = 'Error: ' + (err.error || 'failed');
            return;
        }
        const data = await resp.json();
        exportStatus.textContent = 'Done! Downloading...';
        window.location.href = '/audio/' + encodeURIComponent(data.output);
    } catch(e) {
        exportStatus.textContent = 'Error: ' + e.message;
    } finally {
        exportBtn.disabled = false;
    }
}

loadHistory();

// Tabs
function showTab(tab) {
    document.getElementById('recordTab').style.display = tab === 'record' ? 'block' : 'none';
    document.getElementById('bookTab').style.display = tab === 'book' ? 'block' : 'none';
    document.getElementById('scriptsTab').style.display = tab === 'scripts' ? 'block' : 'none';
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    if (tab === 'scripts') loadScripts();
    if (tab === 'book') loadBook();
}

// Book
async function loadBook() {
    const resp = await fetch('/book');
    const data = await resp.json();
    const list = document.getElementById('bookList');
    const viewer = document.getElementById('bookViewer');
    list.innerHTML = '';
    list.style.display = 'flex';
    viewer.style.display = 'none';
    data.forEach(section => {
        const header = document.createElement('div');
        header.style.cssText = 'color:#666; font-size:0.75rem; text-transform:uppercase; letter-spacing:1px; margin-top:16px; margin-bottom:4px; padding-left:4px;';
        header.textContent = section.section;
        list.appendChild(header);
        section.files.forEach(item => {
            const div = document.createElement('div');
            div.className = 'script-item';
            div.innerHTML = '<div class="title">' + item.title + '</div><div class="desc">' + item.desc + '</div>';
            div.onclick = () => loadBookFile(item.path);
            list.appendChild(div);
        });
    });
}

async function loadBookFile(path) {
    const resp = await fetch('/book/' + encodeURIComponent(path));
    const text = await resp.text();
    document.getElementById('bookContent').textContent = text;
    document.getElementById('bookList').style.display = 'none';
    document.getElementById('bookViewer').style.display = 'block';
    window.scrollTo(0, 0);
}

function backToBookList() {
    document.getElementById('bookList').style.display = 'flex';
    document.getElementById('bookViewer').style.display = 'none';
}

// Scripts
async function loadScripts() {
    const resp = await fetch('/scripts');
    const data = await resp.json();
    const list = document.getElementById('scriptList');
    const viewer = document.getElementById('scriptViewer');
    list.innerHTML = '';
    list.style.display = 'flex';
    viewer.style.display = 'none';
    data.forEach(item => {
        const div = document.createElement('div');
        div.className = 'script-item';
        div.innerHTML = '<div class="title">' + item.title + '</div><div class="desc">' + item.desc + '</div>';
        div.onclick = () => loadScript(item.file);
        list.appendChild(div);
    });
}

async function loadScript(file) {
    const resp = await fetch('/script/' + encodeURIComponent(file));
    const text = await resp.text();
    document.getElementById('scriptContent').textContent = text;
    document.getElementById('scriptList').style.display = 'none';
    document.getElementById('scriptViewer').style.display = 'block';
}

function backToList() {
    document.getElementById('scriptList').style.display = 'flex';
    document.getElementById('scriptViewer').style.display = 'none';
}

function copyScript() {
    navigator.clipboard.writeText(document.getElementById('scriptContent').textContent);
    event.target.textContent = 'Copied!';
    setTimeout(() => event.target.textContent = 'Copy all', 2000);
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400

    audio = request.files["audio"]
    if not audio.filename:
        return jsonify({"error": "Empty filename"}), 400

    # Save upload
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    ext = Path(audio.filename).suffix or ".webm"
    upload_name = f"dump-{timestamp}{ext}"
    upload_path = UPLOAD_DIR / upload_name
    audio.save(upload_path)

    # Transcribe
    try:
        start = time.time()
        model = get_model()
        segments, info = model.transcribe(
            str(upload_path),
            language=None,  # auto-detect (handles multilingual)
            beam_size=5,
            vad_filter=True,  # filters silence
        )
        text = " ".join(seg.text.strip() for seg in segments)
        elapsed = time.time() - start

        # Save transcript
        transcript_name = f"dump-{timestamp}.txt"
        transcript_path = TRANSCRIPT_DIR / transcript_name
        transcript_path.write_text(
            f"# Voice Dump — {datetime.now().strftime('%B %d, %Y %I:%M %p')}\n"
            f"# Audio: {upload_name}\n"
            f"# Duration: {info.duration:.0f}s | Transcription: {elapsed:.1f}s\n"
            f"# Language detected: {info.language} ({info.language_probability:.0%})\n\n"
            f"{text}\n"
        )

        duration_str = f"{info.duration:.0f}s audio / {elapsed:.1f}s to transcribe"
        return jsonify({
            "text": text,
            "duration": duration_str,
            "filename": transcript_name,
            "language": info.language,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/history")
def history():
    files = sorted(TRANSCRIPT_DIR.glob("*.txt"), reverse=True)[:20]
    items = []
    for f in files:
        # Try to find matching audio file
        stem = f.stem  # e.g. dump-20260321-125245
        audio = None
        for ext in (".webm", ".mp3", ".m4a", ".wav", ".ogg", ".mp4"):
            candidate = UPLOAD_DIR / (stem + ext)
            if candidate.exists():
                audio = candidate.name
                break
        items.append({
            "name": f.name,
            "date": datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d, %I:%M %p"),
            "audio": audio,
        })
    return jsonify(items)

@app.route("/book")
def book():
    """List all book content organized by section."""
    sections = []

    # Audio Script Master
    if V1_AUDIO_SCRIPT.exists():
        lines = V1_AUDIO_SCRIPT.read_text().splitlines()
        sections.append({
            "section": "Audio Script",
            "files": [{
                "path": "audio-script",
                "title": "Audio Script Master (Full Read)",
                "desc": f"{len(lines)} lines — the complete reading script",
            }]
        })

    # Full Compiled Manuscript
    compiled = V1_COMPILED / "manuscript.md"
    if compiled.exists():
        lines = compiled.read_text().splitlines()
        sections.append({
            "section": "Volume One — Compiled",
            "files": [{
                "path": "v1-compiled",
                "title": "Full Manuscript (reading order)",
                "desc": f"{len(lines)} lines — all scenes in order",
            }]
        })

    # Volume One Scenes
    if V1_SCENES.exists():
        files = []
        for f in sorted(V1_SCENES.glob("scene-*.md")):
            first_line = f.read_text().split("\n", 1)[0]
            title = first_line.lstrip("# ").strip() if first_line.startswith("#") else f.stem
            files.append({
                "path": f"v1-scene/{f.name}",
                "title": title,
                "desc": f.stem,
            })
        if files:
            sections.append({"section": "Volume One — Scenes", "files": files})

    # Volume One Interludes
    if V1_INTERLUDES.exists():
        files = []
        for f in sorted(V1_INTERLUDES.glob("*.md")):
            first_line = f.read_text().split("\n", 1)[0]
            title = first_line.lstrip("# ").strip() if first_line.startswith("#") else f.stem
            files.append({
                "path": f"v1-interlude/{f.name}",
                "title": title,
                "desc": f.stem,
            })
        if files:
            sections.append({"section": "Volume One — Interludes", "files": files})

    # Volume Two Tracks
    if V2_TRACKS.exists():
        files = []
        for f in sorted(V2_TRACKS.glob("track-*.md")):
            first_line = f.read_text().split("\n", 1)[0]
            title = first_line.lstrip("# ").strip() if first_line.startswith("#") else f.stem
            files.append({
                "path": f"v2-track/{f.name}",
                "title": title,
                "desc": f.stem,
            })
        if files:
            sections.append({"section": "Volume Two — Tracks", "files": files})

    # Volume Two Interludes
    if V2_INTERLUDES.exists():
        files = []
        for f in sorted(V2_INTERLUDES.glob("*.md")):
            first_line = f.read_text().split("\n", 1)[0]
            title = first_line.lstrip("# ").strip() if first_line.startswith("#") else f.stem
            files.append({
                "path": f"v2-interlude/{f.name}",
                "title": title,
                "desc": f.stem,
            })
        if files:
            sections.append({"section": "Volume Two — Interludes", "files": files})

    return jsonify(sections)

@app.route("/book/<path:name>")
def get_book(name):
    """Read a book file."""
    if name == "audio-script":
        if V1_AUDIO_SCRIPT.exists():
            return V1_AUDIO_SCRIPT.read_text()
        return "Not found", 404
    elif name == "v1-compiled":
        path = V1_COMPILED / "manuscript.md"
        if path.exists():
            return path.read_text()
        return "Not found", 404
    elif name.startswith("v1-scene/"):
        fname = name.split("/", 1)[1]
        path = V1_SCENES / fname
    elif name.startswith("v1-interlude/"):
        fname = name.split("/", 1)[1]
        path = V1_INTERLUDES / fname
    elif name.startswith("v2-track/"):
        fname = name.split("/", 1)[1]
        path = V2_TRACKS / fname
    elif name.startswith("v2-interlude/"):
        fname = name.split("/", 1)[1]
        path = V2_INTERLUDES / fname
    else:
        return "Not found", 404

    if not path.exists():
        return "Not found", 404
    return path.read_text()

@app.route("/scripts")
def scripts():
    """List available promo scripts."""
    items = []
    if PROMO_DIR.exists():
        for f in sorted(PROMO_DIR.glob("*.md")):
            # Read first few lines to get a description
            lines = f.read_text().splitlines()
            title = f.stem.replace("-", " ").replace("_", " ").title()
            desc = ""
            for line in lines[:5]:
                if line.startswith("#"):
                    title = line.lstrip("# ").strip()
                    break
            items.append({
                "file": f.name,
                "title": title,
                "desc": f"{len(lines)} lines",
            })
    return jsonify(items)

@app.route("/script/<name>")
def get_script(name):
    """Read a promo script file."""
    if not PROMO_DIR.exists():
        return "Promo directory not found", 404
    path = PROMO_DIR / name
    if not path.exists() or not path.is_relative_to(PROMO_DIR):
        return "Not found", 404
    return path.read_text()

@app.route("/transcript/<name>")
def get_transcript(name):
    path = TRANSCRIPT_DIR / name
    if not path.exists() or not path.is_relative_to(TRANSCRIPT_DIR):
        return "Not found", 404
    return path.read_text()

@app.route("/audio/<name>")
def get_audio(name):
    """Serve an audio file from uploads."""
    path = UPLOAD_DIR / name
    if not path.exists() or not path.is_relative_to(UPLOAD_DIR):
        return "Not found", 404
    return send_file(path)


@app.route("/export-speed", methods=["POST"])
def export_speed():
    """Re-encode audio at a different speed using ffmpeg (atempo filter)."""
    data = request.get_json()
    if not data or "file" not in data or "speed" not in data:
        return jsonify({"error": "Missing file or speed"}), 400

    filename = data["file"]
    speed = float(data["speed"])
    if speed < 0.5 or speed > 3.0:
        return jsonify({"error": "Speed must be 0.5-3.0"}), 400

    src = UPLOAD_DIR / filename
    if not src.exists() or not src.is_relative_to(UPLOAD_DIR):
        return jsonify({"error": "File not found"}), 404

    # Output filename
    stem = Path(filename).stem
    out_name = f"{stem}-{speed:.2f}x.mp3"
    out_path = UPLOAD_DIR / out_name

    if out_path.exists():
        return jsonify({"output": out_name})

    # ffmpeg atempo filter (range 0.5-2.0, chain for beyond)
    atempo_filters = []
    remaining = speed
    while remaining > 2.0:
        atempo_filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        atempo_filters.append("atempo=0.5")
        remaining /= 0.5
    atempo_filters.append(f"atempo={remaining:.4f}")
    filter_str = ",".join(atempo_filters)

    try:
        subprocess.run(
            ["ffmpeg", "-i", str(src), "-filter:a", filter_str,
             "-ar", "48000", "-ab", "192k", str(out_path)],
            capture_output=True, check=True, timeout=300,
        )
    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"ffmpeg failed: {e.stderr.decode()[-200:]}"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Encoding timed out"}), 500

    return jsonify({"output": out_name})


if __name__ == "__main__":
    cert_dir = APP_DIR / "certs"
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"

    if cert_file.exists() and key_file.exists():
        print("Voice Dump Pipeline (HTTPS)")
        print(f"  Uploads:     {UPLOAD_DIR}")
        print(f"  Transcripts: {TRANSCRIPT_DIR}")
        print(f"  Open:        https://100.67.120.6:8200")
        print()
        app.run(host="0.0.0.0", port=8200, debug=False,
                ssl_context=(str(cert_file), str(key_file)))
    else:
        print("Voice Dump Pipeline (HTTP — no certs found)")
        print(f"  Uploads:     {UPLOAD_DIR}")
        print(f"  Transcripts: {TRANSCRIPT_DIR}")
        print(f"  Open:        http://0.0.0.0:8200")
        print()
        app.run(host="0.0.0.0", port=8200, debug=False)
