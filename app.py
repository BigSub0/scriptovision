#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           ScriptoVision — Complete Script-to-Video App       ║
║  Paste script → AI scenes → Approve → Images → Animate →    ║
║  Voiceover → Final Video                                     ║
║  PLUS: Upload video → Analyze → Continue the series         ║
╚══════════════════════════════════════════════════════════════╝
"""

import os, json, threading, uuid, shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template_string

app = Flask(__name__)

# Use environment variable BASE_DIR for cloud, fallback to local path
_BASE = Path(os.environ.get("BASE_DIR", "/home/ubuntu/scriptovision"))
UPLOAD_DIR = _BASE / "uploads"
OUTPUT_DIR = _BASE / "output"
TEMP_DIR   = _BASE / "temp"
IMAGES_DIR = _BASE / "images"
AUDIO_DIR  = _BASE / "audio"
for d in [UPLOAD_DIR, OUTPUT_DIR, TEMP_DIR, IMAGES_DIR, AUDIO_DIR]:
    d.mkdir(parents=True, exist_ok=True)

jobs = {}   # job_id → {status, logs, scenes, output, ...}

# ─────────────────────────────────────────────────────────────────────────────
# HTML UI
# ─────────────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ScriptoVision — Script to Video</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#07070f;color:#ddd;min-height:100vh}
:root{--red:#e94560;--blue:#0f3460;--dark:#12121e;--border:#252540}

/* ── HEADER ── */
header{background:linear-gradient(135deg,#0d0d1e,#0f3460);padding:20px 32px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
header h1{font-size:1.6rem;font-weight:800;color:#fff;letter-spacing:-0.5px}
header h1 span{color:var(--red)}
.tagline{color:#666;font-size:.82rem;margin-top:3px}
.mode-tabs{display:flex;gap:8px}
.mode-tab{padding:8px 18px;border-radius:20px;border:1px solid var(--border);background:transparent;color:#888;cursor:pointer;font-size:.85rem;transition:all .2s}
.mode-tab.active{background:var(--red);border-color:var(--red);color:#fff;font-weight:600}

/* ── LAYOUT ── */
.app{display:grid;grid-template-columns:340px 1fr;min-height:calc(100vh - 70px)}
.sidebar{background:#0d0d1e;border-right:1px solid var(--border);padding:20px;overflow-y:auto}
.main{padding:24px;overflow-y:auto}

/* ── STEP TRACKER ── */
.steps{display:flex;gap:0;margin-bottom:24px}
.step{flex:1;text-align:center;padding:10px 4px;font-size:.75rem;color:#444;border-bottom:2px solid var(--border);position:relative;cursor:default}
.step.active{color:var(--red);border-bottom-color:var(--red);font-weight:700}
.step.done{color:#4a9;border-bottom-color:#4a9}
.step-num{display:block;font-size:1.1rem;font-weight:800;margin-bottom:2px}

/* ── CARDS ── */
.card{background:var(--dark);border:1px solid var(--border);border-radius:10px;padding:18px;margin-bottom:16px}
.card-title{font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#666;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border)}

/* ── FORMS ── */
label{display:block;font-size:.8rem;color:#777;margin-bottom:5px;margin-top:12px}
label:first-child{margin-top:0}
input,select,textarea{width:100%;background:#0d0d1e;border:1px solid var(--border);border-radius:7px;padding:9px 11px;color:#ddd;font-size:.88rem;outline:none;transition:border-color .2s}
input:focus,select:focus,textarea:focus{border-color:var(--red)}
textarea{resize:vertical;min-height:120px;font-family:monospace;line-height:1.5}
.big-textarea{min-height:260px}

/* ── BUTTONS ── */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:10px 20px;border-radius:8px;font-size:.88rem;font-weight:600;cursor:pointer;border:none;transition:all .2s}
.btn-primary{background:linear-gradient(135deg,var(--red),#c73652);color:#fff;width:100%;padding:13px}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(233,69,96,.4)}
.btn-primary:disabled{opacity:.5;transform:none;cursor:not-allowed}
.btn-secondary{background:#1a1a2e;border:1px solid var(--border);color:#aaa}
.btn-secondary:hover{border-color:var(--red);color:var(--red)}
.btn-success{background:#0a2a0a;border:1px solid #2a4a2a;color:#4aff6a}
.btn-success:hover{background:#0f3a0f}
.btn-danger{background:#2a0a0a;border:1px solid #4a1a1a;color:#ff6a4a}
.btn-sm{padding:6px 12px;font-size:.78rem}
.btn-row{display:flex;gap:8px;margin-top:10px}

/* ── SCENE CARDS ── */
.scene-card{background:#0a0a18;border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:12px;position:relative;transition:border-color .2s}
.scene-card:hover{border-color:#333}
.scene-card.approved{border-color:#2a4a2a;background:#080f08}
.scene-card.rejected{border-color:#4a1a1a;background:#0f0808;opacity:.6}
.scene-header{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.scene-badge{background:var(--red);color:#fff;font-size:.7rem;font-weight:800;padding:3px 9px;border-radius:10px;flex-shrink:0}
.scene-title{font-weight:700;font-size:.95rem;flex:1}
.scene-mood{font-size:.72rem;color:#666;background:#1a1a2e;padding:2px 8px;border-radius:8px}
.scene-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.scene-field label{font-size:.72rem;color:#555;margin-bottom:3px}
.scene-field p{font-size:.82rem;color:#bbb;line-height:1.4}
.scene-full{grid-column:1/-1}
.dialogue-line{display:flex;gap:8px;align-items:flex-start;margin-bottom:5px;font-size:.82rem}
.speaker{color:var(--red);font-weight:700;min-width:80px;flex-shrink:0}
.line-text{color:#ccc}
.approval-bar{display:flex;gap:8px;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}
.status-badge{font-size:.72rem;padding:3px 10px;border-radius:8px;font-weight:600}
.status-pending{background:#1a1a0a;color:#aaaa44;border:1px solid #3a3a1a}
.status-approved{background:#0a1a0a;color:#44aa44;border:1px solid #1a3a1a}
.status-rejected{background:#1a0a0a;color:#aa4444;border:1px solid #3a1a1a}

/* ── SHOW BIBLE ── */
.bible-section{margin-bottom:16px}
.bible-section h3{font-size:.82rem;color:var(--red);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}
.character-card{background:#0a0a18;border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px}
.char-name{font-weight:700;color:#fff;font-size:.9rem}
.char-role{font-size:.72rem;color:var(--red);margin-left:8px}
.char-desc{font-size:.8rem;color:#888;margin-top:4px}

/* ── LOG / STATUS ── */
.log-panel{background:#050510;border:1px solid var(--border);border-radius:8px;padding:14px;font-family:monospace;font-size:.78rem;color:#4aff4a;min-height:120px;max-height:220px;overflow-y:auto;white-space:pre-wrap}
.progress-bar{height:5px;background:#1a1a2e;border-radius:3px;overflow:hidden;margin:10px 0}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--red),#ff8c42);border-radius:3px;transition:width .5s ease;width:0}

/* ── DOWNLOAD ── */
.download-box{display:none;background:#080f08;border:1px solid #2a4a2a;border-radius:10px;padding:20px;text-align:center;margin-top:12px}
.download-box a{color:#4aff6a;font-size:1.1rem;font-weight:700;text-decoration:none}

/* ── UPLOAD ZONE ── */
.upload-zone{border:2px dashed var(--border);border-radius:10px;padding:30px;text-align:center;cursor:pointer;transition:all .2s;background:#0a0a18}
.upload-zone:hover,.upload-zone.drag{border-color:var(--red);background:#12080e}
.upload-zone p{color:#555;font-size:.88rem;margin-top:8px}
.upload-zone .icon{font-size:2.5rem}

/* ── VOICE MAP ── */
.voice-row{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;align-items:center}
.voice-row .char-label{font-size:.82rem;color:#aaa;font-weight:600}

/* ── RESPONSIVE ── */
@media(max-width:768px){
  .app{grid-template-columns:1fr}
  .sidebar{border-right:none;border-bottom:1px solid var(--border)}
  .scene-grid{grid-template-columns:1fr}
}

/* ── SECTION PANELS ── */
.panel{display:none}
.panel.active{display:block}
.section-header{font-size:1.1rem;font-weight:700;color:#fff;margin-bottom:16px;display:flex;align-items:center;gap:10px}
.section-header .count{background:var(--red);color:#fff;font-size:.72rem;padding:2px 8px;border-radius:10px}

/* ── NOTIFICATION ── */
.notif{position:fixed;top:20px;right:20px;background:#1a2a1a;border:1px solid #2a4a2a;color:#4aff6a;padding:12px 20px;border-radius:8px;font-size:.85rem;z-index:9999;display:none;animation:slideIn .3s ease}
@keyframes slideIn{from{transform:translateX(100%)}to{transform:translateX(0)}}
.notif.error{background:#2a1a1a;border-color:#4a2a2a;color:#ff6a4a}

/* ── API KEY NOTICE ── */
.api-notice{background:#1a1a0a;border:1px solid #3a3a1a;border-radius:8px;padding:12px;font-size:.8rem;color:#aaaa55;margin-top:10px}
.api-notice a{color:#cccc55}
</style>
</head>
<body>

<div id="notif" class="notif"></div>

<!-- HEADER -->
<header>
  <div>
    <h1>Scripto<span>Vision</span></h1>
    <div class="tagline">Script → Scenes → Approve → Animate → Video</div>
  </div>
  <div class="mode-tabs">
    <button class="mode-tab active" onclick="setMode('script')" id="tab-script">✍️ Script Mode</button>
    <button class="mode-tab" onclick="setMode('continue')" id="tab-continue">📺 Continue Series</button>
  </div>
</header>

<div class="app">

  <!-- ── SIDEBAR ── -->
  <div class="sidebar">

    <!-- STEP TRACKER -->
    <div class="steps" id="step-tracker">
      <div class="step active" id="step1"><span class="step-num">1</span>Input</div>
      <div class="step" id="step2"><span class="step-num">2</span>Review</div>
      <div class="step" id="step3"><span class="step-num">3</span>Approve</div>
      <div class="step" id="step4"><span class="step-num">4</span>Generate</div>
      <div class="step" id="step5"><span class="step-num">5</span>Done</div>
    </div>

    <!-- SETTINGS CARD -->
    <div class="card">
      <div class="card-title">⚙️ Settings</div>

      <label>Project Name</label>
      <input type="text" id="project_name" value="my_project" placeholder="my_project">

      <label>Visual Style</label>
      <select id="visual_style">
        <option value="cinematic photorealistic">Cinematic Photorealistic</option>
        <option value="animated cartoon vibrant">Animated / Cartoon</option>
        <option value="comic book graphic novel">Comic Book / Graphic Novel</option>
        <option value="anime style detailed">Anime Style</option>
        <option value="dark gritty noir">Dark / Noir</option>
        <option value="urban street photography">Urban Street Photography</option>
        <option value="watercolor illustrated">Watercolor / Illustrated</option>
      </select>

      <label>AI Provider (for animation)</label>
      <select id="provider">
        <option value="demo">Demo Mode (Ken Burns — No API needed)</option>
        <option value="ltx2">LTX-2 — Best Audio+Video (Fal.ai)</option>
        <option value="wan25">Wan 2.5 — High Quality (Fal.ai)</option>
        <option value="kling">Kling Pro — Cinematic (Fal.ai)</option>
      </select>

      <label>Fal.ai API Key</label>
      <input type="password" id="fal_key" placeholder="fal_xxxxxxxx (leave blank for demo)">

      <label>OpenAI API Key</label>
      <input type="password" id="openai_key" placeholder="sk-xxxxxxxx (for GPT + DALL-E + TTS)">

      <label>Background Music (optional)</label>
      <input type="text" id="bg_music" placeholder="/path/to/music.mp3">

      <div class="api-notice">
        💡 <strong>No API keys?</strong> Run in Demo Mode — full workflow with placeholder visuals and espeak audio. Get keys at <a href="https://fal.ai" target="_blank">fal.ai</a> and <a href="https://platform.openai.com" target="_blank">openai.com</a>
      </div>
    </div>

    <!-- VOICE MAP CARD -->
    <div class="card" id="voice-map-card" style="display:none">
      <div class="card-title">🎙️ Voice Assignments</div>
      <div id="voice-map-rows"></div>
      <div style="font-size:.75rem;color:#555;margin-top:8px">Voices: onyx (deep male), echo (male), nova (female), shimmer (light), alloy (neutral), fable (dramatic)</div>
    </div>

  </div>

  <!-- ── MAIN CONTENT ── -->
  <div class="main">

    <!-- ══ SCRIPT MODE ══ -->
    <div class="panel active" id="panel-script">

      <!-- STEP 1: INPUT -->
      <div id="view-input">
        <div class="section-header">✍️ Paste Your Script or Story</div>
        <div class="card">
          <label>Your Script / Story / Episode Idea</label>
          <textarea class="big-textarea" id="script_input" placeholder="Paste your full script here. It can be:
• A complete screenplay with scene headings
• A story written in prose
• Dialogue-heavy script
• A rough outline

Example:
INT. SOUTH SIDE CHICAGO - NIGHT
The streets are alive with energy.
NARRATOR: It was the summer of '94...
SUB: Man, these streets never sleep.
FRIEND: You already know how it goes.

The system will automatically break it into scenes,
generate images for each one, add voiceovers and
dialogue, animate everything, and produce your video.

You approve every scene before anything is generated."></textarea>

          <div style="margin-top:14px">
            <button class="btn btn-primary" onclick="parseScript()" id="parse-btn">
              🎬 Analyze Script & Generate Scenes
            </button>
          </div>
        </div>
      </div>

      <!-- STEP 2 & 3: SCENE REVIEW + APPROVAL -->
      <div id="view-review" style="display:none">
        <div class="section-header">
          🎬 Review Your Scenes
          <span class="count" id="scene-count-badge">0 scenes</span>
          <span id="approval-summary" style="font-size:.8rem;color:#888;margin-left:auto"></span>
        </div>

        <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap">
          <button class="btn btn-success btn-sm" onclick="approveAll()">✅ Approve All</button>
          <button class="btn btn-secondary btn-sm" onclick="backToScript()">← Edit Script</button>
          <button class="btn btn-secondary btn-sm" onclick="addBlankScene()">+ Add Scene</button>
          <div style="flex:1"></div>
          <button class="btn btn-primary" style="width:auto;padding:10px 24px" onclick="proceedToGenerate()" id="proceed-btn">
            ✅ Approve & Generate Video →
          </button>
        </div>

        <div id="scenes-container"></div>
      </div>

      <!-- STEP 4: GENERATION -->
      <div id="view-generate" style="display:none">
        <div class="section-header">⚙️ Generating Your Video</div>
        <div class="card">
          <div class="log-panel" id="log-output">Waiting to start...</div>
          <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
          <div id="gen-status" style="font-size:.82rem;color:#666;margin-top:6px">Initializing...</div>
        </div>
        <div class="download-box" id="download-box">
          <div style="font-size:2rem;margin-bottom:8px">🎉</div>
          <div style="color:#4aff6a;font-size:1.1rem;font-weight:700;margin-bottom:12px">Your Video is Ready!</div>
          <a id="download-link" href="#" download>⬇️ Download Final Video</a>
          <div style="margin-top:12px">
            <button class="btn btn-secondary btn-sm" onclick="startOver()">🔄 Make Another Video</button>
          </div>
        </div>
      </div>

    </div>

    <!-- ══ CONTINUE SERIES MODE ══ -->
    <div class="panel" id="panel-continue">

      <div id="view-upload">
        <div class="section-header">📺 Continue Your Series</div>
        <div class="card">
          <p style="color:#888;font-size:.88rem;margin-bottom:16px">Upload an existing episode of your show (4AllBuddies, Trap Daddy Series, etc.) and the AI will analyze the characters, style, and story — then write and produce the next episode for you.</p>

          <div class="upload-zone" id="upload-zone" onclick="document.getElementById('video-upload').click()">
            <div class="icon">🎬</div>
            <div style="font-weight:700;color:#ccc;margin-top:8px">Click to Upload Your Video</div>
            <p>MP4, MOV, AVI — any episode or clip from your show</p>
            <input type="file" id="video-upload" accept="video/*" style="display:none" onchange="handleVideoUpload(this)">
          </div>

          <div id="upload-info" style="display:none;margin-top:12px">
            <div style="background:#0a1a0a;border:1px solid #1a3a1a;border-radius:8px;padding:12px">
              <span style="color:#4aff6a">✅ Video loaded: </span>
              <span id="upload-filename" style="color:#ccc"></span>
            </div>
          </div>

          <label style="margin-top:16px">Show Title (optional — we'll detect it)</label>
          <input type="text" id="show_title" placeholder="e.g. 4AllBuddies, Trap Daddy Series...">

          <label>Episode Direction (optional)</label>
          <textarea id="episode_direction" placeholder="Give the AI direction for the next episode. Examples:
• In this episode the crew discovers a hidden talent
• Focus on the friendship between the two main characters
• Add a surprise twist at the end
• Keep it funny and lighthearted" style="min-height:80px"></textarea>

          <div style="margin-top:14px">
            <button class="btn btn-primary" onclick="analyzeVideo()" id="analyze-btn">
              🔍 Analyze Video & Write Next Episode
            </button>
          </div>
        </div>
      </div>

      <!-- SHOW BIBLE VIEW -->
      <div id="view-bible" style="display:none">
        <div class="section-header">📖 Show Bible Detected</div>

        <div class="card" id="bible-display"></div>

        <div class="card" style="margin-top:16px">
          <div class="card-title">📝 Generated Script — Episode <span id="ep-num">2</span></div>
          <textarea id="generated-script" class="big-textarea" style="font-family:monospace;font-size:.82rem"></textarea>
          <div class="btn-row">
            <button class="btn btn-primary" style="flex:1" onclick="useGeneratedScript()">
              ✅ Use This Script → Review Scenes
            </button>
            <button class="btn btn-secondary" onclick="regenerateScript()">🔄 Regenerate</button>
          </div>
        </div>
      </div>

    </div>

  </div>
</div>

<script>
// ─────────────────────────────────────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────────────────────────────────────
let currentMode = 'script';
let currentStep = 1;
let scenes = [];
let currentJobId = null;
let showBible = null;
let uploadedVideoPath = null;

// ─────────────────────────────────────────────────────────────────────────────
// MODE SWITCHING
// ─────────────────────────────────────────────────────────────────────────────
function setMode(mode) {
  currentMode = mode;
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + mode).classList.add('active');
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + mode).classList.add('active');
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP TRACKER
// ─────────────────────────────────────────────────────────────────────────────
function setStep(n) {
  currentStep = n;
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById('step' + i);
    el.className = 'step' + (i < n ? ' done' : i === n ? ' active' : '');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// NOTIFICATIONS
// ─────────────────────────────────────────────────────────────────────────────
function notify(msg, isError = false) {
  const el = document.getElementById('notif');
  el.textContent = msg;
  el.className = 'notif' + (isError ? ' error' : '');
  el.style.display = 'block';
  setTimeout(() => el.style.display = 'none', 3500);
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 1 → 2: PARSE SCRIPT
// ─────────────────────────────────────────────────────────────────────────────
async function parseScript() {
  const script = document.getElementById('script_input').value.trim();
  if (!script) { notify('Please paste a script first!', true); return; }

  const btn = document.getElementById('parse-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Analyzing script...';

  try {
    const resp = await fetch('/parse', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        script,
        style: document.getElementById('visual_style').value,
        openai_key: document.getElementById('openai_key').value
      })
    });
    const data = await resp.json();
    if (data.error) { notify(data.error, true); return; }

    scenes = data.scenes;
    renderScenes();
    document.getElementById('view-input').style.display = 'none';
    document.getElementById('view-review').style.display = 'block';
    setStep(2);
    notify(`✅ ${scenes.length} scenes detected — review and approve below`);
    buildVoiceMap();
  } catch(e) {
    notify('Parse failed: ' + e, true);
  } finally {
    btn.disabled = false;
    btn.textContent = '🎬 Analyze Script & Generate Scenes';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// RENDER SCENES
// ─────────────────────────────────────────────────────────────────────────────
function renderScenes() {
  const container = document.getElementById('scenes-container');
  container.innerHTML = '';
  document.getElementById('scene-count-badge').textContent = scenes.length + ' scenes';

  scenes.forEach((scene, idx) => {
    const status = scene._status || 'pending';
    const card = document.createElement('div');
    card.className = `scene-card ${status === 'approved' ? 'approved' : status === 'rejected' ? 'rejected' : ''}`;
    card.id = `scene-card-${idx}`;

    const dialogueHTML = (scene.dialogue || []).map(d =>
      `<div class="dialogue-line"><span class="speaker">${d.speaker}:</span><span class="line-text">"${d.line}"</span></div>`
    ).join('');

    card.innerHTML = `
      <div class="scene-header">
        <span class="scene-badge">SCENE ${scene.scene_number}</span>
        <span class="scene-title" contenteditable="true" onblur="updateSceneField(${idx},'title',this.textContent)">${scene.title}</span>
        <span class="scene-mood">${scene.mood || 'dramatic'}</span>
      </div>

      <div class="scene-grid">
        <div class="scene-field">
          <label>📍 Setting</label>
          <p contenteditable="true" onblur="updateSceneField(${idx},'setting',this.textContent)">${scene.setting || ''}</p>
        </div>
        <div class="scene-field">
          <label>⏱️ Duration</label>
          <p><input type="number" value="${scene.duration || 6}" min="3" max="15" style="width:70px" onchange="updateSceneField(${idx},'duration',parseInt(this.value))">s</p>
        </div>
        <div class="scene-field scene-full">
          <label>🖼️ Image Prompt (click to edit)</label>
          <p contenteditable="true" onblur="updateSceneField(${idx},'image_prompt',this.textContent)" style="color:#aaa;font-size:.8rem">${scene.image_prompt || ''}</p>
        </div>
        <div class="scene-field scene-full">
          <label>🎬 Motion Prompt</label>
          <p contenteditable="true" onblur="updateSceneField(${idx},'motion_prompt',this.textContent)" style="color:#aaa;font-size:.8rem">${scene.motion_prompt || ''}</p>
        </div>
        ${scene.voiceover ? `
        <div class="scene-field scene-full">
          <label>🎙️ Voiceover</label>
          <p contenteditable="true" onblur="updateSceneField(${idx},'voiceover',this.textContent)" style="color:#9ab">${scene.voiceover}</p>
        </div>` : ''}
        ${dialogueHTML ? `
        <div class="scene-field scene-full">
          <label>💬 Dialogue</label>
          ${dialogueHTML}
        </div>` : ''}
      </div>

      <div class="approval-bar">
        <span class="status-badge ${status === 'approved' ? 'status-approved' : status === 'rejected' ? 'status-rejected' : 'status-pending'}" id="status-badge-${idx}">
          ${status === 'approved' ? '✅ Approved' : status === 'rejected' ? '❌ Removed' : '⏳ Pending'}
        </span>
        <div style="flex:1"></div>
        <button class="btn btn-success btn-sm" onclick="approveScene(${idx})">✅ Approve</button>
        <button class="btn btn-danger btn-sm" onclick="rejectScene(${idx})">❌ Remove</button>
        <button class="btn btn-secondary btn-sm" onclick="moveScene(${idx},-1)">↑</button>
        <button class="btn btn-secondary btn-sm" onclick="moveScene(${idx},1)">↓</button>
      </div>
    `;
    container.appendChild(card);
  });

  updateApprovalSummary();
}

function updateSceneField(idx, field, value) {
  scenes[idx][field] = value;
}

function approveScene(idx) {
  scenes[idx]._status = 'approved';
  const card = document.getElementById(`scene-card-${idx}`);
  card.className = 'scene-card approved';
  document.getElementById(`status-badge-${idx}`).className = 'status-badge status-approved';
  document.getElementById(`status-badge-${idx}`).textContent = '✅ Approved';
  updateApprovalSummary();
}

function rejectScene(idx) {
  scenes[idx]._status = 'rejected';
  const card = document.getElementById(`scene-card-${idx}`);
  card.className = 'scene-card rejected';
  document.getElementById(`status-badge-${idx}`).className = 'status-badge status-rejected';
  document.getElementById(`status-badge-${idx}`).textContent = '❌ Removed';
  updateApprovalSummary();
}

function approveAll() {
  scenes.forEach((s, i) => { s._status = 'approved'; approveScene(i); });
  notify('✅ All scenes approved!');
}

function moveScene(idx, dir) {
  const newIdx = idx + dir;
  if (newIdx < 0 || newIdx >= scenes.length) return;
  [scenes[idx], scenes[newIdx]] = [scenes[newIdx], scenes[idx]];
  scenes.forEach((s, i) => s.scene_number = i + 1);
  renderScenes();
}

function addBlankScene() {
  const n = scenes.length + 1;
  scenes.push({
    scene_number: n, title: `New Scene ${n}`, setting: '',
    image_prompt: 'Cinematic scene, professional lighting',
    motion_prompt: 'Camera slowly pushes in',
    voiceover: '', dialogue: [], duration: 6, mood: 'dramatic', _status: 'pending'
  });
  renderScenes();
}

function updateApprovalSummary() {
  const approved = scenes.filter(s => s._status === 'approved').length;
  const total = scenes.length;
  document.getElementById('approval-summary').textContent = `${approved}/${total} approved`;
  setStep(approved > 0 ? 3 : 2);
}

// ─────────────────────────────────────────────────────────────────────────────
// VOICE MAP
// ─────────────────────────────────────────────────────────────────────────────
function buildVoiceMap() {
  const allChars = new Set(['narrator']);
  scenes.forEach(s => (s.dialogue || []).forEach(d => allChars.add(d.speaker.toLowerCase())));

  const voices = ['onyx','echo','nova','shimmer','alloy','fable'];
  const container = document.getElementById('voice-map-rows');
  container.innerHTML = '';
  allChars.forEach(char => {
    const row = document.createElement('div');
    row.className = 'voice-row';
    const defaultVoice = char === 'narrator' ? 'onyx' : voices[Math.floor(Math.random() * voices.length)];
    row.innerHTML = `
      <span class="char-label">${char.charAt(0).toUpperCase() + char.slice(1)}</span>
      <select id="voice-${char}" style="padding:5px 8px;font-size:.8rem">
        ${voices.map(v => `<option value="${v}" ${v===defaultVoice?'selected':''}>${v}</option>`).join('')}
      </select>`;
    container.appendChild(row);
  });
  document.getElementById('voice-map-card').style.display = 'block';
}

function getVoiceMap() {
  const map = {};
  document.querySelectorAll('[id^="voice-"]').forEach(el => {
    map[el.id.replace('voice-', '')] = el.value;
  });
  return map;
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 3 → 4: PROCEED TO GENERATE
// ─────────────────────────────────────────────────────────────────────────────
async function proceedToGenerate() {
  const approved = scenes.filter(s => s._status === 'approved');
  if (approved.length === 0) {
    notify('Please approve at least one scene first!', true);
    return;
  }

  document.getElementById('view-review').style.display = 'none';
  document.getElementById('view-generate').style.display = 'block';
  setStep(4);

  const payload = {
    scenes: approved,
    project_name: document.getElementById('project_name').value || 'my_project',
    provider: document.getElementById('provider').value,
    fal_key: document.getElementById('fal_key').value,
    openai_key: document.getElementById('openai_key').value,
    bg_music: document.getElementById('bg_music').value,
    voice_map: getVoiceMap()
  };

  try {
    const resp = await fetch('/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    currentJobId = data.job_id;
    pollJob(currentJobId, approved.length);
  } catch(e) {
    log('Error: ' + e);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// POLLING
// ─────────────────────────────────────────────────────────────────────────────
function log(msg) {
  const el = document.getElementById('log-output');
  el.textContent += '\n' + msg;
  el.scrollTop = el.scrollHeight;
}

async function pollJob(jobId, totalScenes) {
  while (true) {
    await new Promise(r => setTimeout(r, 2500));
    try {
      const resp = await fetch('/status/' + jobId);
      const data = await resp.json();

      if (data.logs) {
        document.getElementById('log-output').textContent = data.logs;
        document.getElementById('log-output').scrollTop = 9999;
      }

      const pct = Math.min(95, 5 + (data.scenes_done || 0) / totalScenes * 85);
      document.getElementById('progress-fill').style.width = pct + '%';
      document.getElementById('gen-status').textContent = data.status_msg || 'Processing...';

      if (data.status === 'done') {
        document.getElementById('progress-fill').style.width = '100%';
        document.getElementById('download-box').style.display = 'block';
        document.getElementById('download-link').href = '/download/' + jobId;
        setStep(5);
        notify('🎉 Your video is ready!');
        break;
      } else if (data.status === 'error') {
        log('\n❌ Error: ' + (data.error || 'Unknown'));
        notify('Generation failed: ' + data.error, true);
        break;
      }
    } catch(e) { log('Poll error: ' + e); }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTINUE SERIES MODE
// ─────────────────────────────────────────────────────────────────────────────
async function handleVideoUpload(input) {
  const file = input.files[0];
  if (!file) return;

  document.getElementById('upload-filename').textContent = file.name;
  document.getElementById('upload-info').style.display = 'block';

  const formData = new FormData();
  formData.append('video', file);

  const btn = document.getElementById('analyze-btn');
  btn.textContent = '⏫ Uploading...';
  btn.disabled = true;

  const resp = await fetch('/upload_video', {method:'POST', body: formData});
  const data = await resp.json();
  uploadedVideoPath = data.path;

  btn.textContent = '🔍 Analyze Video & Write Next Episode';
  btn.disabled = false;
  notify('✅ Video uploaded: ' + file.name);
}

async function analyzeVideo() {
  if (!uploadedVideoPath) { notify('Please upload a video first!', true); return; }

  const btn = document.getElementById('analyze-btn');
  btn.disabled = true;
  btn.textContent = '🔍 Analyzing...';

  try {
    const resp = await fetch('/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        video_path: uploadedVideoPath,
        show_title: document.getElementById('show_title').value,
        episode_direction: document.getElementById('episode_direction').value,
        openai_key: document.getElementById('openai_key').value
      })
    });
    const data = await resp.json();
    if (data.error) { notify(data.error, true); return; }

    showBible = data.show_bible;
    renderBible(data);

    document.getElementById('view-upload').style.display = 'none';
    document.getElementById('view-bible').style.display = 'block';
    notify('✅ Show analyzed! Review the generated script below.');
  } catch(e) {
    notify('Analysis failed: ' + e, true);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 Analyze Video & Write Next Episode';
  }
}

function renderBible(data) {
  const bible = data.show_bible;
  document.getElementById('ep-num').textContent = data.next_episode_number;
  document.getElementById('generated-script').value = data.next_episode_script;

  const chars = (bible.characters || []).map(c => `
    <div class="character-card">
      <span class="char-name">${c.name}</span>
      <span class="char-role">${c.role}</span>
      <div class="char-desc">${c.description}</div>
      <div class="char-desc" style="color:#666;margin-top:4px">Voice: ${c.voice_style}</div>
    </div>`).join('');

  document.getElementById('bible-display').innerHTML = `
    <div class="card-title">📖 ${bible.show_title || 'Show Bible'}</div>
    <div class="bible-section">
      <h3>Genre & Tone</h3>
      <p style="font-size:.85rem;color:#aaa">${bible.genre} · ${bible.tone} · ${bible.visual_style}</p>
    </div>
    <div class="bible-section">
      <h3>Story So Far</h3>
      <p style="font-size:.85rem;color:#aaa">${bible.episode_summary}</p>
    </div>
    <div class="bible-section">
      <h3>Characters Detected</h3>
      ${chars}
    </div>
    <div class="bible-section">
      <h3>Next Episode Hook</h3>
      <p style="font-size:.85rem;color:#aaa">${bible.next_episode_hook}</p>
    </div>`;
}

async function regenerateScript() {
  if (!showBible) return;
  const btn = document.querySelector('[onclick="regenerateScript()"]');
  btn.textContent = '⏳ Regenerating...';
  btn.disabled = true;

  const resp = await fetch('/regenerate_script', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      show_bible: showBible,
      episode_number: parseInt(document.getElementById('ep-num').textContent),
      direction: document.getElementById('episode_direction').value,
      openai_key: document.getElementById('openai_key').value
    })
  });
  const data = await resp.json();
  document.getElementById('generated-script').value = data.script;
  btn.textContent = '🔄 Regenerate';
  btn.disabled = false;
  notify('Script regenerated!');
}

function useGeneratedScript() {
  const script = document.getElementById('generated-script').value;
  document.getElementById('script_input').value = script;
  setMode('script');
  parseScript();
}

// ─────────────────────────────────────────────────────────────────────────────
// NAVIGATION
// ─────────────────────────────────────────────────────────────────────────────
function backToScript() {
  document.getElementById('view-review').style.display = 'none';
  document.getElementById('view-input').style.display = 'block';
  setStep(1);
}

function startOver() {
  scenes = [];
  currentJobId = null;
  document.getElementById('view-generate').style.display = 'none';
  document.getElementById('view-input').style.display = 'block';
  document.getElementById('log-output').textContent = 'Waiting to start...';
  document.getElementById('progress-fill').style.width = '0';
  document.getElementById('download-box').style.display = 'none';
  setStep(1);
}

// Drag & drop on upload zone
const zone = document.getElementById('upload-zone');
if (zone) {
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('drag');
    const file = e.dataTransfer.files[0];
    if (file) {
      const dt = new DataTransfer();
      dt.items.add(file);
      document.getElementById('video-upload').files = dt.files;
      handleVideoUpload(document.getElementById('video-upload'));
    }
  });
}
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/parse", methods=["POST"])
def parse():
    """Parse script into scenes using GPT or demo parser."""
    data = request.json
    script = data.get("script", "")
    style  = data.get("style", "cinematic photorealistic")
    key    = data.get("openai_key", "")

    if key:
        os.environ["OPENAI_API_KEY"] = key

    try:
        from scene_parser import parse_script_to_scenes, parse_script_demo
        if os.environ.get("OPENAI_API_KEY"):
            scenes = parse_script_to_scenes(script, style)
        else:
            scenes = parse_script_demo(script)
        # Ensure each scene has a _status field
        for s in scenes:
            s["_status"] = "pending"
        return jsonify({"scenes": scenes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generate", methods=["POST"])
def generate():
    """Start the full generation pipeline in a background thread."""
    data     = request.json
    scenes   = data.get("scenes", [])
    project  = data.get("project_name", "project")
    provider = data.get("provider", "kling")
    fal_key  = data.get("fal_key", "")
    oai_key  = data.get("openai_key", "")
    bg_music = data.get("bg_music", "")
    voice_map = data.get("voice_map", {})

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "running", "logs": "Starting...\n",
        "scenes_done": 0, "output": None,
        "status_msg": "Initializing pipeline..."
    }

    def run():
        env = os.environ.copy()
        if fal_key:
            env["FAL_KEY"]      = fal_key
            env["FAL_API_KEY"]  = fal_key
            os.environ["FAL_KEY"]     = fal_key
            os.environ["FAL_API_KEY"] = fal_key
        if oai_key:
            env["OPENAI_API_KEY"] = oai_key
            os.environ["OPENAI_API_KEY"] = oai_key

        log_lines = []
        def log(msg):
            log_lines.append(msg)
            jobs[job_id]["logs"] = "\n".join(log_lines[-100:])

        try:
            import sys
            sys.path.insert(0, "/home/ubuntu/scriptovision")
            from image_gen  import generate_image
            from tts_engine import generate_audio_for_scene, build_scene_audio_track
            from assembler  import process_scene, assemble_final_video

            clip_paths = []

            for i, scene in enumerate(scenes):
                sn = scene.get("scene_number", i+1)
                title = scene.get("title", f"Scene {sn}")
                log(f"[{sn}/{len(scenes)}] 🖼️  Generating image: {title}")
                jobs[job_id]["status_msg"] = f"Scene {sn}/{len(scenes)} — generating image..."

                # Image
                try:
                    img_path = generate_image(scene, project)
                    scene["_image_path"] = img_path
                    log(f"[{sn}/{len(scenes)}] ✅ Image ready")
                except Exception as e:
                    log(f"[{sn}/{len(scenes)}] ⚠️  Image failed: {e}")
                    scene["_image_path"] = ""

                # Audio
                log(f"[{sn}/{len(scenes)}] 🎙️  Generating audio...")
                jobs[job_id]["status_msg"] = f"Scene {sn}/{len(scenes)} — generating audio..."
                try:
                    audio_result = generate_audio_for_scene(scene, project, voice_map)
                    audio_path   = build_scene_audio_track(scene, audio_result, project)
                    scene["_audio_path"] = audio_path
                    log(f"[{sn}/{len(scenes)}] ✅ Audio ready")
                except Exception as e:
                    log(f"[{sn}/{len(scenes)}] ⚠️  Audio failed: {e}")
                    scene["_audio_path"] = ""

                # Animate
                log(f"[{sn}/{len(scenes)}] 🎬 Animating scene...")
                jobs[job_id]["status_msg"] = f"Scene {sn}/{len(scenes)} — animating..."
                try:
                    clip = process_scene(scene, project, provider, add_captions=True)
                    clip_paths.append(clip)
                    jobs[job_id]["scenes_done"] = i + 1
                    log(f"[{sn}/{len(scenes)}] ✅ Scene complete → {clip}")
                except Exception as e:
                    log(f"[{sn}/{len(scenes)}] ❌ Animation failed: {e}")

            if not clip_paths:
                raise ValueError("No clips were generated")

            # Assemble
            log(f"\n🔗 Assembling {len(clip_paths)} clips into final video...")
            jobs[job_id]["status_msg"] = "Assembling final video..."
            bg = bg_music if bg_music and Path(bg_music).exists() else None
            final = assemble_final_video(clip_paths, project, bg)
            jobs[job_id]["output"] = final
            jobs[job_id]["status"] = "done"
            jobs[job_id]["status_msg"] = "Done!"
            log(f"\n✅ COMPLETE! → {final}")

        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"]  = str(e)
            jobs[job_id]["logs"]  += f"\n❌ FATAL: {e}"

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    return jsonify(jobs.get(job_id, {"status": "not_found"}))


@app.route("/download/<job_id>")
def download(job_id):
    job = jobs.get(job_id, {})
    out = job.get("output")
    if out and Path(out).exists():
        return send_file(out, as_attachment=True, download_name=Path(out).name)
    return jsonify({"error": "File not found"}), 404


@app.route("/upload_video", methods=["POST"])
def upload_video():
    """Accept an uploaded video file and save it."""
    f = request.files.get("video")
    if not f:
        return jsonify({"error": "No file"}), 400
    save_path = UPLOAD_DIR / f.filename
    f.save(str(save_path))
    return jsonify({"path": str(save_path), "name": f.filename})


@app.route("/analyze", methods=["POST"])
def analyze():
    """Analyze an uploaded video and generate the next episode script."""
    data      = request.json
    vid_path  = data.get("video_path", "")
    title     = data.get("show_title", "")
    direction = data.get("episode_direction", "")
    key       = data.get("openai_key", "")

    if key:
        os.environ["OPENAI_API_KEY"] = key

    if not vid_path or not Path(vid_path).exists():
        return jsonify({"error": "Video file not found"}), 400

    try:
        import sys
        sys.path.insert(0, "/home/ubuntu/scriptovision")
        from video_analyzer import analyze_and_continue
        result = analyze_and_continue(vid_path, title, user_direction=direction)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/regenerate_script", methods=["POST"])
def regenerate_script():
    """Regenerate the next episode script from the show bible."""
    data       = request.json
    show_bible = data.get("show_bible", {})
    ep_num     = data.get("episode_number", 2)
    direction  = data.get("direction", "")
    key        = data.get("openai_key", "")

    if key:
        os.environ["OPENAI_API_KEY"] = key

    try:
        import sys
        sys.path.insert(0, "/home/ubuntu/scriptovision")
        from video_analyzer import generate_next_episode
        script = generate_next_episode(show_bible, ep_num, direction)
        return jsonify({"script": script})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("\n╔══════════════════════════════════════╗")
    print("║       ScriptoVision is Running       ║")
    print("║   Open: http://localhost:8080         ║")
    print("╚══════════════════════════════════════╝\n")
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
