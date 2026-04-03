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

jobs = {}   # job_id → {status, logs, scenes, output, scene_images, ...}

# ── API keys loaded from environment variables (set on Render/Railway) ──
os.environ["ANIMATION_PROVIDER"] = os.environ.get("ANIMATION_PROVIDER", "kling")

# ─────────────────────────────────────────────────────────────────────────────
# HTML UI  — v3 Redesign
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
:root{--red:#e94560;--blue:#0f3460;--dark:#12121e;--border:#252540;--green:#2ecc71;--yellow:#f1c40f}

/* ── HEADER ── */
header{background:linear-gradient(135deg,#0d0d1e,#0f3460);padding:16px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:12px}
header h1{font-size:1.5rem;font-weight:800;color:#fff;letter-spacing:-0.5px}
header h1 span{color:var(--red)}
.tagline{color:#555;font-size:.75rem;margin-top:2px}
.header-right{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.mode-tabs{display:flex;gap:6px}
.mode-tab{padding:7px 16px;border-radius:20px;border:1px solid var(--border);background:transparent;color:#888;cursor:pointer;font-size:.82rem;transition:all .2s;white-space:nowrap}
.mode-tab.active{background:var(--red);border-color:var(--red);color:#fff;font-weight:600}
.job-restore-btn{padding:7px 14px;border-radius:20px;border:1px solid #2a4a2a;background:#0a1a0a;color:#4aff6a;cursor:pointer;font-size:.78rem;display:none}
.job-restore-btn:hover{background:#0f2a0f}

/* ── STEP BAR ── */
.step-bar{background:#0d0d1e;border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:stretch;overflow-x:auto}
.step-item{display:flex;align-items:center;gap:8px;padding:12px 16px;font-size:.78rem;color:#444;border-bottom:3px solid transparent;cursor:default;white-space:nowrap;transition:all .2s}
.step-item.active{color:var(--red);border-bottom-color:var(--red);font-weight:700}
.step-item.done{color:#4a9;border-bottom-color:#4a9;cursor:pointer}
.step-item.done:hover{color:#6fd}
.step-num{width:22px;height:22px;border-radius:50%;background:#1a1a2e;display:flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:800;flex-shrink:0}
.step-item.active .step-num{background:var(--red);color:#fff}
.step-item.done .step-num{background:#2a4a2a;color:#4a9}

/* ── LAYOUT ── */
.app-body{display:grid;grid-template-columns:300px 1fr;min-height:calc(100vh - 110px)}
.sidebar{background:#0a0a16;border-right:1px solid var(--border);padding:16px;overflow-y:auto;position:sticky;top:110px;height:calc(100vh - 110px)}
.main-content{padding:20px 24px;overflow-y:auto}

/* ── CARDS ── */
.card{background:var(--dark);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:14px}
.card-title{font-size:.73rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#555;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:6px}

/* ── FORMS ── */
label{display:block;font-size:.78rem;color:#666;margin-bottom:4px;margin-top:10px}
label:first-child{margin-top:0}
input,select,textarea{width:100%;background:#0a0a16;border:1px solid var(--border);border-radius:7px;padding:8px 10px;color:#ddd;font-size:.85rem;outline:none;transition:border-color .2s}
input:focus,select:focus,textarea:focus{border-color:var(--red)}
textarea{resize:vertical;min-height:100px;font-family:monospace;line-height:1.5}
.big-textarea{min-height:240px}

/* ── BUTTONS ── */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 18px;border-radius:8px;font-size:.85rem;font-weight:600;cursor:pointer;border:none;transition:all .2s;text-decoration:none}
.btn-primary{background:linear-gradient(135deg,var(--red),#c73652);color:#fff;width:100%;padding:12px}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(233,69,96,.4)}
.btn-primary:disabled{opacity:.5;transform:none;cursor:not-allowed}
.btn-secondary{background:#1a1a2e;border:1px solid var(--border);color:#aaa}
.btn-secondary:hover{border-color:var(--red);color:var(--red)}
.btn-success{background:#0a2a0a;border:1px solid #2a4a2a;color:#4aff6a}
.btn-success:hover{background:#0f3a0f}
.btn-danger{background:#2a0a0a;border:1px solid #4a1a1a;color:#ff6a4a}
.btn-sm{padding:5px 10px;font-size:.75rem}
.btn-row{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
.btn-icon{width:32px;height:32px;padding:0;border-radius:6px;font-size:.9rem}

/* ── SECTION HEADER ── */
.section-header{font-size:1.05rem;font-weight:700;color:#fff;margin-bottom:14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.section-header .badge{background:var(--red);color:#fff;font-size:.7rem;padding:2px 8px;border-radius:10px}
.section-header .sub{font-size:.8rem;color:#666;font-weight:400;margin-left:auto}

/* ── SCENE CARDS ── */
.scene-card{background:#0a0a18;border:1px solid var(--border);border-radius:10px;margin-bottom:12px;overflow:hidden;transition:border-color .2s}
.scene-card:hover{border-color:#333}
.scene-card.approved{border-color:#2a4a2a}
.scene-card.rejected{border-color:#4a1a1a;opacity:.55}
.scene-card-header{display:flex;align-items:center;gap:8px;padding:12px 14px;background:#0d0d1e;cursor:pointer;user-select:none}
.scene-badge{background:var(--red);color:#fff;font-size:.68rem;font-weight:800;padding:3px 8px;border-radius:8px;flex-shrink:0}
.scene-title-text{font-weight:700;font-size:.92rem;flex:1;outline:none}
.scene-mood-tag{font-size:.68rem;color:#666;background:#1a1a2e;padding:2px 7px;border-radius:8px;flex-shrink:0}
.scene-status-dot{width:8px;height:8px;border-radius:50%;background:#444;flex-shrink:0}
.scene-status-dot.approved{background:#4a9}
.scene-status-dot.rejected{background:#e94560}
.scene-chevron{color:#444;font-size:.8rem;transition:transform .2s;flex-shrink:0}
.scene-chevron.open{transform:rotate(180deg)}

.scene-body{display:none;padding:14px;border-top:1px solid var(--border)}
.scene-body.open{display:block}

/* Scene image preview */
.scene-preview{display:flex;gap:14px;margin-bottom:12px}
.scene-img-box{width:160px;min-width:160px;height:90px;border-radius:7px;overflow:hidden;background:#0d0d1e;border:1px solid var(--border);position:relative;flex-shrink:0}
.scene-img-box img{width:100%;height:100%;object-fit:cover;display:block}
.scene-img-placeholder{width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#333;font-size:1.8rem}
.scene-img-status{position:absolute;bottom:4px;left:4px;font-size:.6rem;background:rgba(0,0,0,.7);color:#4aff6a;padding:2px 5px;border-radius:4px;display:none}
.scene-img-status.visible{display:block}
.scene-details{flex:1;min-width:0}

.scene-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}
.scene-field label{font-size:.7rem;color:#555;margin-bottom:2px;margin-top:0}
.scene-field p{font-size:.8rem;color:#bbb;line-height:1.4;outline:none;min-height:1.2em}
.scene-field p:focus{color:#fff;background:#0d0d1e;border-radius:4px;padding:2px 4px}
.scene-full{grid-column:1/-1}
.dialogue-line{display:flex;gap:6px;align-items:flex-start;margin-bottom:4px;font-size:.8rem}
.speaker{color:var(--red);font-weight:700;min-width:70px;flex-shrink:0}
.line-text{color:#ccc}

.approval-bar{display:flex;gap:6px;align-items:center;margin-top:10px;padding-top:10px;border-top:1px solid var(--border);flex-wrap:wrap}
.status-pill{font-size:.7rem;padding:3px 10px;border-radius:10px;font-weight:600}
.pill-pending{background:#1a1a0a;color:#aaaa44;border:1px solid #3a3a1a}
.pill-approved{background:#0a1a0a;color:#44aa44;border:1px solid #1a3a1a}
.pill-rejected{background:#1a0a0a;color:#aa4444;border:1px solid #3a1a1a}

/* ── GENERATION VIEW ── */
.gen-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
.gen-scene-strip{display:flex;flex-direction:column;gap:8px}
.gen-scene-item{display:flex;align-items:center;gap:10px;background:#0a0a18;border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:.8rem}
.gen-scene-item.done{border-color:#2a4a2a}
.gen-scene-item.active{border-color:var(--red);background:#12080e}
.gen-scene-item.error{border-color:#4a1a1a}
.gen-thumb{width:60px;height:34px;border-radius:4px;overflow:hidden;background:#0d0d1e;flex-shrink:0;border:1px solid var(--border)}
.gen-thumb img{width:100%;height:100%;object-fit:cover}
.gen-scene-info{flex:1;min-width:0}
.gen-scene-name{font-weight:600;color:#ccc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gen-scene-state{font-size:.7rem;color:#555;margin-top:1px}
.gen-scene-state.done{color:#4a9}
.gen-scene-state.active{color:var(--red)}
.gen-scene-state.error{color:#e94560}
.gen-icon{font-size:1rem;flex-shrink:0}

/* ── LOG PANEL ── */
.log-panel{background:#050510;border:1px solid var(--border);border-radius:8px;padding:12px;font-family:monospace;font-size:.75rem;color:#4aff4a;min-height:100px;max-height:200px;overflow-y:auto;white-space:pre-wrap;line-height:1.5}
.progress-bar{height:4px;background:#1a1a2e;border-radius:3px;overflow:hidden;margin:8px 0}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--red),#ff8c42);border-radius:3px;transition:width .5s ease;width:0}
.gen-status-line{font-size:.8rem;color:#666;display:flex;align-items:center;gap:8px}
.pulse{width:8px;height:8px;border-radius:50%;background:var(--red);animation:pulse 1.2s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}

/* ── DOWNLOAD BOX ── */
.download-box{display:none;background:#080f08;border:2px solid #2a4a2a;border-radius:12px;padding:24px;text-align:center;margin-top:14px}
.download-box .big-icon{font-size:3rem;margin-bottom:8px}
.download-box h2{color:#4aff6a;font-size:1.2rem;margin-bottom:6px}
.download-box p{color:#666;font-size:.82rem;margin-bottom:16px}
.download-btn{display:inline-flex;align-items:center;gap:8px;background:linear-gradient(135deg,#2ecc71,#27ae60);color:#fff;padding:12px 28px;border-radius:10px;font-size:1rem;font-weight:700;text-decoration:none;transition:all .2s}
.download-btn:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(46,204,113,.4)}

/* ── UPLOAD ZONE ── */
.upload-zone{border:2px dashed var(--border);border-radius:10px;padding:28px;text-align:center;cursor:pointer;transition:all .2s;background:#0a0a18}
.upload-zone:hover,.upload-zone.drag{border-color:var(--red);background:#12080e}
.upload-zone .uz-icon{font-size:2.8rem;margin-bottom:8px}
.upload-zone h3{color:#ccc;font-size:.95rem;font-weight:700}
.upload-zone p{color:#555;font-size:.82rem;margin-top:5px}

/* ── UPLOADED FILE INFO ── */
.file-info-bar{display:none;background:#0a1a0a;border:1px solid #1a3a1a;border-radius:8px;padding:10px 14px;margin-top:10px;display:none;align-items:center;gap:10px}
.file-info-bar.visible{display:flex}
.file-info-bar .fi-name{flex:1;font-size:.85rem;color:#ccc;font-weight:600}
.file-info-bar .fi-change{font-size:.75rem;color:#888;cursor:pointer;text-decoration:underline}
.file-info-bar .fi-change:hover{color:var(--red)}

/* ── VOICE MAP ── */
.voice-row{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;align-items:center}
.voice-row .char-label{font-size:.8rem;color:#aaa;font-weight:600}

/* ── SHOW BIBLE ── */
.bible-section{margin-bottom:12px}
.bible-section h3{font-size:.78rem;color:var(--red);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.character-card{background:#0a0a18;border:1px solid var(--border);border-radius:7px;padding:10px;margin-bottom:6px}
.char-name{font-weight:700;color:#fff;font-size:.88rem}
.char-role{font-size:.7rem;color:var(--red);margin-left:6px}
.char-desc{font-size:.78rem;color:#777;margin-top:3px}

/* ── NOTIFICATION ── */
.notif{position:fixed;top:16px;right:16px;background:#1a2a1a;border:1px solid #2a4a2a;color:#4aff6a;padding:10px 18px;border-radius:8px;font-size:.82rem;z-index:9999;display:none;animation:slideIn .25s ease;max-width:320px}
@keyframes slideIn{from{transform:translateX(110%)}to{transform:translateX(0)}}
.notif.error{background:#2a1a1a;border-color:#4a2a2a;color:#ff6a4a}
.notif.info{background:#1a1a2a;border-color:#2a2a4a;color:#aaaaff}

/* ── PANELS ── */
.panel{display:none}
.panel.active{display:block}

/* ── RESPONSIVE ── */
@media(max-width:800px){
  .app-body{grid-template-columns:1fr}
  .sidebar{position:relative;top:0;height:auto;border-right:none;border-bottom:1px solid var(--border)}
  .gen-grid{grid-template-columns:1fr}
  .scene-preview{flex-direction:column}
  .scene-img-box{width:100%;height:140px}
}

/* ── MISC ── */
.empty-state{text-align:center;padding:40px 20px;color:#444}
.empty-state .es-icon{font-size:3rem;margin-bottom:12px}
.empty-state p{font-size:.88rem}
.divider{height:1px;background:var(--border);margin:14px 0}
.tip{background:#0d0d20;border:1px solid #1a1a3a;border-radius:7px;padding:10px 12px;font-size:.78rem;color:#666;margin-top:10px}
.tip strong{color:#888}
</style>
</head>
<body>

<div id="notif" class="notif"></div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- HEADER -->
<!-- ═══════════════════════════════════════════════════════════ -->
<header>
  <div class="logo">
    <div>
      <h1>Scripto<span>Vision</span></h1>
      <div class="tagline">Script → Scenes → Approve → Animate → Video</div>
    </div>
  </div>
  <div class="header-right">
    <button id="restore-btn" class="job-restore-btn" onclick="restoreJob()">
      🔄 Resume In-Progress Job
    </button>
    <div class="mode-tabs">
      <button class="mode-tab active" onclick="setMode('script')" id="tab-script">✍️ Script Mode</button>
      <button class="mode-tab" onclick="setMode('continue')" id="tab-continue">📺 Continue Series</button>
    </div>
  </div>
</header>

<!-- STEP BAR -->
<div class="step-bar" id="step-bar">
  <div class="step-item active" id="step1" onclick="goToStep(1)">
    <div class="step-num">1</div> Write Script
  </div>
  <div class="step-item" id="step2" onclick="goToStep(2)">
    <div class="step-num">2</div> Review Scenes
  </div>
  <div class="step-item" id="step3" onclick="goToStep(3)">
    <div class="step-num">3</div> Approve
  </div>
  <div class="step-item" id="step4" onclick="goToStep(4)">
    <div class="step-num">4</div> Generating
  </div>
  <div class="step-item" id="step5" onclick="goToStep(5)">
    <div class="step-num">5</div> Done ✓
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- BODY -->
<!-- ═══════════════════════════════════════════════════════════ -->
<div class="app-body">

  <!-- ── SIDEBAR ── -->
  <div class="sidebar">

    <div class="card">
      <div class="card-title">⚙️ Settings</div>

      <label>Project Name</label>
      <input type="text" id="project_name" value="my_project" placeholder="my_project">

      <label>Visual Style</label>
      <select id="visual_style">
        <option value="cinematic photorealistic">🎬 Cinematic / Live-Action</option>
        <option value="animated cartoon vibrant">🎨 Animated / Cartoon</option>
        <option value="comic book graphic novel">💥 Comic Book</option>
        <option value="anime style detailed">⛩️ Anime</option>
        <option value="dark gritty noir">🌑 Dark / Noir</option>
        <option value="urban street photography">📷 Urban Street</option>
        <option value="watercolor illustrated">🖌️ Watercolor</option>
      </select>

      <label>Animation Engine</label>
      <select id="provider">
        <option value="kling" selected>Kling 1.6 — Cinematic ✨</option>
        <option value="kling_pro">Kling 1.6 Pro — Ultra</option>
        <option value="wan25">Wan 2.5 — High Quality</option>
        <option value="ltx2">LTX-2 — Fast</option>
      </select>

      <label>Fal.ai API Key</label>
      <input type="password" id="fal_key" placeholder="Pre-configured ✓ (leave blank)">

      <label>OpenAI API Key</label>
      <input type="password" id="openai_key" placeholder="Pre-configured ✓ (leave blank)">

      <label>ElevenLabs API Key <span style="color:#4aff6a;font-size:.68rem">(Ultra-realistic voices)</span></label>
      <input type="password" id="elevenlabs_key" placeholder="Pre-configured ✓ (leave blank)" value="sk_e8ede427e79a39b9d92ff69e531f85dc568b0373211b1fa2">

      <label>Background Music (optional)</label>
      <input type="text" id="bg_music" placeholder="/path/to/music.mp3">
    </div>

    <!-- VOICE MAP -->
    <div class="card" id="voice-map-card" style="display:none">
      <div class="card-title">🎙️ Voice Assignments</div>
      <div id="voice-map-rows"></div>
      <div style="font-size:.72rem;color:#444;margin-top:6px">
        onyx · echo · nova · shimmer · alloy · fable
      </div>
    </div>

  </div>

  <!-- ── MAIN CONTENT ── -->
  <div class="main-content">

    <!-- ══════════════════════════════════════════════ -->
    <!-- SCRIPT MODE -->
    <!-- ══════════════════════════════════════════════ -->
    <div class="panel active" id="panel-script">

      <!-- STEP 1: WRITE -->
      <div id="view-input">
        <div class="section-header">
          ✍️ Write Your Script
          <span class="sub">Paste a script, story, or outline — AI does the rest</span>
        </div>
        <div class="card">
          <textarea class="big-textarea" id="script_input" placeholder="Paste your script here. Can be:
• A full screenplay with scene headings
• A story written in prose
• Dialogue-heavy script
• A rough outline or episode idea

Example:
INT. SOUTH SIDE CHICAGO - NIGHT
The streets are alive with energy.
NARRATOR: It was the summer of '94...
SUB: Man, these streets never sleep.
FRIEND: You already know how it goes.

The AI will break it into scenes, generate images,
add voiceovers, animate everything, and produce your video.
You approve every scene before anything generates."></textarea>

          <div style="margin-top:12px">
            <button class="btn btn-primary" onclick="parseScript()" id="parse-btn">
              🎬 Analyze Script & Generate Scenes
            </button>
          </div>
          <div class="tip">
            <strong>Tip:</strong> Select your Visual Style in the sidebar before analyzing — it affects how every scene image looks.
          </div>
        </div>
      </div>

      <!-- STEP 2 & 3: REVIEW -->
      <div id="view-review" style="display:none">
        <div class="section-header">
          🎬 Review & Approve Scenes
          <span class="badge" id="scene-count-badge">0 scenes</span>
          <span class="sub" id="approval-summary"></span>
        </div>

        <div class="btn-row" style="margin-bottom:14px">
          <button class="btn btn-success btn-sm" onclick="approveAll()">✅ Approve All</button>
          <button class="btn btn-secondary btn-sm" onclick="backToScript()">← Edit Script</button>
          <button class="btn btn-secondary btn-sm" onclick="addBlankScene()">+ Add Scene</button>
          <div style="flex:1"></div>
          <button class="btn btn-primary" style="width:auto;padding:10px 22px" onclick="proceedToGenerate()" id="proceed-btn">
            ▶ Generate Video →
          </button>
        </div>

        <div id="scenes-container"></div>
      </div>

      <!-- STEP 4: GENERATING -->
      <div id="view-generate" style="display:none">
        <div class="section-header">
          ⚙️ Generating Your Video
          <span class="sub" id="gen-eta"></span>
        </div>

        <div class="gen-grid">
          <!-- Left: scene progress strip -->
          <div>
            <div class="card" style="padding:12px">
              <div class="card-title">🎞️ Scene Progress</div>
              <div class="gen-scene-strip" id="gen-scene-strip"></div>
            </div>
          </div>
          <!-- Right: log + status -->
          <div>
            <div class="card" style="padding:12px">
              <div class="card-title">📋 Live Log</div>
              <div class="log-panel" id="log-output">Waiting to start...</div>
              <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
              <div class="gen-status-line">
                <div class="pulse" id="pulse-dot"></div>
                <span id="gen-status">Initializing...</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Download box -->
        <div class="download-box" id="download-box">
          <div class="big-icon">🎉</div>
          <h2>Your Video is Ready!</h2>
          <p>All scenes animated and assembled into your final video.</p>
          <a id="download-link" href="#" download class="download-btn">⬇️ Download Final Video</a>
          <div class="btn-row" style="justify-content:center;margin-top:14px">
            <button class="btn btn-secondary btn-sm" onclick="startOver()">🔄 Make Another Video</button>
            <button class="btn btn-secondary btn-sm" onclick="goToStep(2)">← Back to Scenes</button>
          </div>
        </div>
      </div>

    </div>

    <!-- ══════════════════════════════════════════════ -->
    <!-- CONTINUE SERIES MODE -->
    <!-- ══════════════════════════════════════════════ -->
    <div class="panel" id="panel-continue">

      <!-- UPLOAD VIEW -->
      <div id="view-upload">
        <div class="section-header">📺 Continue Your Series</div>
        <div class="card">
          <p style="color:#777;font-size:.85rem;margin-bottom:14px">
            Upload an existing episode of your show — 4AllBuddies, Trap Daddy Series, or any series.
            The AI analyzes characters, style, and story, then writes and produces the next episode.
          </p>

          <div class="upload-zone" id="upload-zone" onclick="triggerUpload()">
            <div class="uz-icon">🎬</div>
            <h3>Click to Upload Your Video</h3>
            <p>MP4, MOV, AVI — any episode or clip</p>
            <input type="file" id="video-upload" accept="video/*" style="display:none" onchange="handleVideoUpload(this)">
          </div>

          <div class="file-info-bar" id="file-info-bar">
            <span style="color:#4aff6a;font-size:1rem">✅</span>
            <span class="fi-name" id="upload-filename">—</span>
            <span class="fi-change" onclick="triggerUpload()">Replace video</span>
          </div>

          <label style="margin-top:14px">Show Title <span style="color:#555">(optional — AI will detect it)</span></label>
          <input type="text" id="show_title" placeholder="e.g. 4AllBuddies, Trap Daddy Series...">

          <label>Episode Direction <span style="color:#555">(optional)</span></label>
          <textarea id="episode_direction" placeholder="Give the AI direction for the next episode:
• In this episode the crew discovers a hidden talent
• Focus on the friendship between the main characters
• Add a surprise twist at the end" style="min-height:80px"></textarea>

          <div style="margin-top:12px">
            <button class="btn btn-primary" onclick="analyzeVideo()" id="analyze-btn">
              🔍 Analyze Video & Write Next Episode
            </button>
          </div>
        </div>
      </div>

      <!-- SHOW BIBLE VIEW -->
      <div id="view-bible" style="display:none">
        <div class="section-header">
          📖 Show Bible Detected
          <button class="btn btn-secondary btn-sm" onclick="backToUpload()" style="margin-left:auto">← Upload Different Video</button>
        </div>

        <div class="card" id="bible-display"></div>

        <div class="card" style="margin-top:14px">
          <div class="card-title">📝 Generated Script — Episode <span id="ep-num">2</span></div>
          <textarea id="generated-script" class="big-textarea" style="font-family:monospace;font-size:.8rem"></textarea>
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

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- JAVASCRIPT -->
<!-- ═══════════════════════════════════════════════════════════ -->
<script>
// ─────────────────────────────────────────────────────────────────────────────
// GLOBAL ERROR HANDLER — prevents blank screen on any uncaught JS error
// ─────────────────────────────────────────────────────────────────────────────
window.onerror = function(msg, src, line, col, err) {
  console.error('[SV Error]', msg, src, line, col, err);
  try {
    const notif = document.getElementById('notif');
    if (notif) {
      notif.textContent = '⚠️ UI glitch caught: ' + msg + ' — recovering...';
      notif.className = 'notif error';
      notif.style.display = 'block';
      setTimeout(() => { notif.style.display = 'none'; }, 6000);
    }
    // Never let all views go blank — always show at least one
    const views = ['view-input','view-review','view-generate'];
    const anyVisible = views.some(id => {
      const el = document.getElementById(id);
      return el && el.style.display !== 'none';
    });
    if (!anyVisible) {
      const v = document.getElementById('view-input');
      if (v) { v.style.display = 'block'; }
    }
  } catch(e2) { /* recovery itself failed — nothing we can do */ }
  return false;
};
window.addEventListener('unhandledrejection', function(e) {
  console.error('[SV Promise Error]', e.reason);
  try {
    const notif = document.getElementById('notif');
    if (notif) {
      const msg = (e.reason && e.reason.message) ? e.reason.message : String(e.reason);
      notif.textContent = '⚠️ Network error: ' + msg;
      notif.className = 'notif error';
      notif.style.display = 'block';
      setTimeout(() => { notif.style.display = 'none'; }, 5000);
    }
  } catch(e2) {}
});
// ─────────────────────────────────────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────────────────────────────────────
let currentMode  = 'script';
let currentStep  = 1;
let scenes       = [];
let currentJobId = null;
let showBible    = null;
let uploadedVideoPath = null;
let approvedScenes = [];
let genSceneStates = []; // [{title, state, imgPath}]
const STORAGE_KEY = 'sv_active_job';

// ─────────────────────────────────────────────────────────────────────────────
// INIT — check for saved job on page load
// ─────────────────────────────────────────────────────────────────────────────
window.addEventListener('load', () => {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) {
    try {
      const job = JSON.parse(saved);
      if (job.job_id && job.timestamp) {
        const age = Date.now() - job.timestamp;
        if (age < 3 * 60 * 60 * 1000) { // 3 hours
          document.getElementById('restore-btn').style.display = 'block';
          document.getElementById('restore-btn').textContent =
            `🔄 Resume Job (${job.project || 'project'})`;
        } else {
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    } catch(e) { localStorage.removeItem(STORAGE_KEY); }
  }
});

function saveJob(jobId, project, totalScenes) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    job_id: jobId,
    project,
    total_scenes: totalScenes,
    timestamp: Date.now()
  }));
}

function clearSavedJob() {
  localStorage.removeItem(STORAGE_KEY);
  document.getElementById('restore-btn').style.display = 'none';
}

async function restoreJob() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (!saved) return;
  const job = JSON.parse(saved);

  notify('🔄 Reconnecting to job ' + job.job_id + '...', 'info');

  // Check if job still exists on server
  try {
    const resp = await fetch('/status/' + job.job_id);
    const data = await resp.json();
    if (data.status === 'not_found') {
      notify('Job expired — server was restarted. Please regenerate.', true);
      clearSavedJob();
      return;
    }

    currentJobId = job.job_id;
    approvedScenes = [];
    const total = job.total_scenes || 7;

    // Build placeholder gen strip
    genSceneStates = [];
    for (let i = 0; i < total; i++) {
      genSceneStates.push({ title: `Scene ${i+1}`, state: 'pending', imgPath: null });
    }

    document.getElementById('view-input').style.display = 'none';
    document.getElementById('view-review').style.display = 'none';
    document.getElementById('view-generate').style.display = 'block';
    setStep(4);
    renderGenStrip();

    if (data.status === 'done') {
      onJobDone(job.job_id);
    } else if (data.status === 'error') {
      notify('Job failed: ' + data.error, true);
      clearSavedJob();
    } else {
      pollJob(job.job_id, total);
    }
  } catch(e) {
    notify('Could not reconnect: ' + e, true);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MODE & STEP
// ─────────────────────────────────────────────────────────────────────────────
function setMode(mode) {
  currentMode = mode;
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + mode).classList.add('active');
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + mode).classList.add('active');
}

function setStep(n) {
  currentStep = n;
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById('step' + i);
    if (i < n)       el.className = 'step-item done';
    else if (i === n) el.className = 'step-item active';
    else              el.className = 'step-item';
  }
}

function goToStep(n) {
  // Only allow going back to completed steps
  if (n >= currentStep) return;
  if (n === 1) { backToScript(); return; }
  if (n === 2 && currentStep >= 3) {
    document.getElementById('view-generate').style.display = 'none';
    document.getElementById('view-review').style.display = 'block';
    setStep(2);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// NOTIFICATIONS
// ─────────────────────────────────────────────────────────────────────────────
function notify(msg, typeOrBool) {
  const el = document.getElementById('notif');
  el.textContent = msg;
  const isError = typeOrBool === true || typeOrBool === 'error';
  const isInfo  = typeOrBool === 'info';
  el.className = 'notif' + (isError ? ' error' : isInfo ? ' info' : '');
  el.style.display = 'block';
  clearTimeout(window._notifTimer);
  window._notifTimer = setTimeout(() => el.style.display = 'none', 4000);
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 1 → 2: PARSE SCRIPT
// ─────────────────────────────────────────────────────────────────────────────
async function parseScript() {
  const script = document.getElementById('script_input').value.trim();
  if (!script) { notify('Please paste a script first!', true); return; }

  const btn = document.getElementById('parse-btn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Analyzing script...';

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
    btn.innerHTML = '🎬 Analyze Script & Generate Scenes';
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

    const imgSrc = scene._preview_url || '';
    const imgHTML = imgSrc
      ? `<img src="${imgSrc}" alt="Scene preview" onerror="this.style.display='none'">`
      : `<div class="scene-img-placeholder">🎬</div>`;

    const pillClass = status === 'approved' ? 'pill-approved' : status === 'rejected' ? 'pill-rejected' : 'pill-pending';
    const pillText  = status === 'approved' ? '✅ Approved' : status === 'rejected' ? '❌ Removed' : '⏳ Pending';
    const dotClass  = status === 'approved' ? 'approved' : status === 'rejected' ? 'rejected' : '';

    card.innerHTML = `
      <div class="scene-card-header" onclick="toggleScene(${idx})">
        <span class="scene-badge">SCENE ${scene.scene_number}</span>
        <span class="scene-title-text">${scene.title}</span>
        <span class="scene-mood-tag">${scene.mood || 'dramatic'}</span>
        <span class="scene-status-dot ${dotClass}" id="dot-${idx}"></span>
        <span class="scene-chevron" id="chev-${idx}">▼</span>
      </div>
      <div class="scene-body" id="body-${idx}">
        <div class="scene-preview">
          <div class="scene-img-box" id="img-box-${idx}">
            ${imgHTML}
            <div class="scene-img-status" id="img-status-${idx}"></div>
          </div>
          <div class="scene-details">
            <div class="scene-grid">
              <div class="scene-field">
                <label>📍 Setting</label>
                <p contenteditable="true" onblur="updateSceneField(${idx},'setting',this.textContent)">${scene.setting || ''}</p>
              </div>
              <div class="scene-field">
                <label>⏱️ Duration</label>
                <p><input type="number" value="${scene.duration || 6}" min="3" max="15" style="width:65px" onchange="updateSceneField(${idx},'duration',parseInt(this.value))">s</p>
              </div>
              <div class="scene-field scene-full">
                <label>🖼️ Image Prompt <span style="color:#444">(click to edit)</span></label>
                <p contenteditable="true" onblur="updateSceneField(${idx},'image_prompt',this.textContent)" style="color:#888;font-size:.78rem">${scene.image_prompt || ''}</p>
              </div>
              <div class="scene-field scene-full">
                <label>🎬 Motion Prompt</label>
                <p contenteditable="true" onblur="updateSceneField(${idx},'motion_prompt',this.textContent)" style="color:#888;font-size:.78rem">${scene.motion_prompt || ''}</p>
              </div>
              ${scene.voiceover ? `
              <div class="scene-field scene-full">
                <label>🎙️ Voiceover</label>
                <p contenteditable="true" onblur="updateSceneField(${idx},'voiceover',this.textContent)" style="color:#9ab">${scene.voiceover}</p>
              </div>` : ''}
            </div>
          </div>
        </div>
        ${dialogueHTML ? `<div class="divider"></div><div style="font-size:.72rem;color:#555;margin-bottom:6px">💬 DIALOGUE</div>${dialogueHTML}` : ''}
        <div class="approval-bar">
          <span class="status-pill ${pillClass}" id="pill-${idx}">${pillText}</span>
          <div style="flex:1"></div>
          <button class="btn btn-success btn-sm" onclick="approveScene(${idx})">✅ Approve</button>
          <button class="btn btn-danger btn-sm" onclick="rejectScene(${idx})">❌ Remove</button>
          <button class="btn btn-secondary btn-icon btn-sm" onclick="moveScene(${idx},-1)" title="Move up">↑</button>
          <button class="btn btn-secondary btn-icon btn-sm" onclick="moveScene(${idx},1)" title="Move down">↓</button>
        </div>
      </div>
    `;
    container.appendChild(card);
  });

  updateApprovalSummary();
}

function toggleScene(idx) {
  const body = document.getElementById(`body-${idx}`);
  const chev = document.getElementById(`chev-${idx}`);
  const isOpen = body.classList.contains('open');
  body.classList.toggle('open', !isOpen);
  chev.classList.toggle('open', !isOpen);
}

function expandAllScenes() {
  scenes.forEach((_, i) => {
    document.getElementById(`body-${i}`).classList.add('open');
    document.getElementById(`chev-${i}`).classList.add('open');
  });
}

function updateSceneField(idx, field, value) {
  scenes[idx][field] = value;
}

function approveScene(idx) {
  scenes[idx]._status = 'approved';
  document.getElementById(`scene-card-${idx}`).className = 'scene-card approved';
  document.getElementById(`dot-${idx}`).className = 'scene-status-dot approved';
  document.getElementById(`pill-${idx}`).className = 'status-pill pill-approved';
  document.getElementById(`pill-${idx}`).textContent = '✅ Approved';
  updateApprovalSummary();
}

function rejectScene(idx) {
  scenes[idx]._status = 'rejected';
  document.getElementById(`scene-card-${idx}`).className = 'scene-card rejected';
  document.getElementById(`dot-${idx}`).className = 'scene-status-dot rejected';
  document.getElementById(`pill-${idx}`).className = 'status-pill pill-rejected';
  document.getElementById(`pill-${idx}`).textContent = '❌ Removed';
  updateApprovalSummary();
}

function approveAll() {
  scenes.forEach((s, i) => { if (s._status !== 'rejected') approveScene(i); });
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
    motion_prompt: 'Camera slowly pushes in, natural motion',
    voiceover: '', dialogue: [], duration: 6, mood: 'dramatic', _status: 'pending'
  });
  renderScenes();
  // Auto-expand the new scene
  setTimeout(() => toggleScene(scenes.length - 1), 50);
}

function updateApprovalSummary() {
  const approved = scenes.filter(s => s._status === 'approved').length;
  const total = scenes.length;
  document.getElementById('approval-summary').textContent = `${approved} of ${total} approved`;
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
      <select id="voice-${char}" style="padding:4px 7px;font-size:.78rem">
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
// GENERATION STRIP
// ─────────────────────────────────────────────────────────────────────────────
function renderGenStrip() {
  const strip = document.getElementById('gen-scene-strip');
  strip.innerHTML = '';
  genSceneStates.forEach((sc, i) => {
    const item = document.createElement('div');
    item.className = `gen-scene-item ${sc.state}`;
    item.id = `gen-item-${i}`;

    const icon = sc.state === 'done' ? '✅' : sc.state === 'active' ? '⚙️' : sc.state === 'error' ? '❌' : '⏳';
    const stateLabel = sc.state === 'done' ? 'Complete' : sc.state === 'active' ? 'Processing...' : sc.state === 'error' ? 'Failed' : 'Waiting';

    item.innerHTML = `
      <div class="gen-thumb" id="gen-thumb-${i}">
        ${sc.imgPath ? `<img src="${sc.imgPath}" alt="">` : ''}
      </div>
      <div class="gen-scene-info">
        <div class="gen-scene-name">${sc.title}</div>
        <div class="gen-scene-state ${sc.state}" id="gen-state-${i}">${icon} ${stateLabel}</div>
      </div>`;
    strip.appendChild(item);
  });
}

function updateGenScene(idx, state, imgPath) {
  if (idx >= genSceneStates.length) return;
  genSceneStates[idx].state = state;
  if (imgPath) genSceneStates[idx].imgPath = imgPath;

  const item = document.getElementById(`gen-item-${idx}`);
  if (!item) return;
  item.className = `gen-scene-item ${state}`;

  const icon = state === 'done' ? '✅' : state === 'active' ? '⚙️' : state === 'error' ? '❌' : '⏳';
  const stateLabel = state === 'done' ? 'Complete' : state === 'active' ? 'Processing...' : state === 'error' ? 'Failed' : 'Waiting';
  const stateEl = document.getElementById(`gen-state-${idx}`);
  if (stateEl) { stateEl.className = `gen-scene-state ${state}`; stateEl.textContent = `${icon} ${stateLabel}`; }

  if (imgPath) {
    const thumb = document.getElementById(`gen-thumb-${idx}`);
    if (thumb) thumb.innerHTML = `<img src="${imgPath}" alt="">`;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 3 → 4: GENERATE
// ─────────────────────────────────────────────────────────────────────────────
async function proceedToGenerate() {
  approvedScenes = scenes.filter(s => s._status === 'approved');
  if (approvedScenes.length === 0) {
    notify('Please approve at least one scene first!', true);
    return;
  }

  // Build gen strip from approved scenes
  genSceneStates = approvedScenes.map(s => ({
    title: s.title || `Scene ${s.scene_number}`,
    state: 'pending',
    imgPath: null
  }));

  document.getElementById('view-review').style.display = 'none';
  document.getElementById('view-generate').style.display = 'block';
  setStep(4);
  renderGenStrip();

  const project = document.getElementById('project_name').value || 'my_project';
  const payload = {
    scenes: approvedScenes,
    project_name: project,
    provider: document.getElementById('provider').value,
    style: document.getElementById('visual_style').value,
    fal_key: document.getElementById('fal_key').value,
    openai_key: document.getElementById('openai_key').value,
    elevenlabs_key: document.getElementById('elevenlabs_key').value,
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
    saveJob(currentJobId, project, approvedScenes.length);
    pollJob(currentJobId, approvedScenes.length);
  } catch(e) {
    logLine('Error starting generation: ' + e);
    notify('Failed to start generation: ' + e, true);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// POLLING — survives page navigation via localStorage
// ─────────────────────────────────────────────────────────────────────────────
function logLine(msg) {
  const el = document.getElementById('log-output');
  if (!el) return;
  el.textContent = msg;
  el.scrollTop = el.scrollHeight;
}

async function pollJob(jobId, totalScenes) {
  let lastLogLen = 0;
  let lastDone = -1;

  while (true) {
    await new Promise(r => setTimeout(r, 3000));
    try {
      const resp = await fetch('/status/' + jobId);
      const data = await resp.json();

      // Update log
      if (data.logs) {
        const el = document.getElementById('log-output');
        if (el) { el.textContent = data.logs; el.scrollTop = el.scrollHeight; }
      }

      // Update progress bar
      const pct = Math.min(95, 5 + (data.scenes_done || 0) / totalScenes * 88);
      const pf = document.getElementById('progress-fill');
      if (pf) pf.style.width = pct + '%';

      // Update status line
      const gs = document.getElementById('gen-status');
      if (gs) gs.textContent = data.status_msg || 'Processing...';

      // Parse log to update gen strip
      if (data.logs) {
        const lines = data.logs.split('\n');
        lines.forEach(line => {
          const m = line.match(/\[(\d+)\/\d+\]/);
          if (!m) return;
          const idx = parseInt(m[1]) - 1;
          if (idx < 0 || idx >= genSceneStates.length) return;

          if (line.includes('Generating image')) updateGenScene(idx, 'active', null);
          else if (line.includes('Image ready')) {
            // Fetch preview image
            fetchScenePreview(jobId, idx);
          }
          else if (line.includes('Animating')) updateGenScene(idx, 'active', null);
          else if (line.includes('Scene complete')) updateGenScene(idx, 'done', null);
          else if (line.includes('Animation failed') || line.includes('Image failed')) updateGenScene(idx, 'error', null);
        });
      }

      // ETA
      const done = data.scenes_done || 0;
      if (done !== lastDone) {
        lastDone = done;
        const remaining = totalScenes - done;
        const etaEl = document.getElementById('gen-eta');
        if (etaEl && remaining > 0) etaEl.textContent = `~${remaining * 2.5} min remaining`;
        else if (etaEl) etaEl.textContent = 'Assembling final video...';
      }

      if (data.status === 'done') {
        onJobDone(jobId);
        break;
      } else if (data.status === 'error') {
        const el = document.getElementById('log-output');
        if (el) el.textContent += '\n\n❌ ERROR: ' + (data.error || 'Unknown error');
        const pd = document.getElementById('pulse-dot');
        if (pd) pd.style.background = '#e94560';
        notify('Generation failed: ' + (data.error || 'Unknown'), true);
        clearSavedJob();
        break;
      }
    } catch(e) {
      const el = document.getElementById('log-output');
      if (el) el.textContent += '\nPoll error (retrying): ' + e;
    }
  }
}

async function fetchScenePreview(jobId, sceneIdx) {
  try {
    const resp = await fetch(`/scene_image/${jobId}/${sceneIdx + 1}`);
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.url) {
      updateGenScene(sceneIdx, 'active', data.url);
    }
  } catch(e) { /* silent */ }
}

function onJobDone(jobId) {
  const pf = document.getElementById('progress-fill');
  if (pf) pf.style.width = '100%';
  const pd = document.getElementById('pulse-dot');
  if (pd) pd.style.background = '#2ecc71';
  const gs = document.getElementById('gen-status');
  if (gs) gs.textContent = '✅ Complete!';
  const etaEl = document.getElementById('gen-eta');
  if (etaEl) etaEl.textContent = '';

  // Mark all scenes done in strip
  genSceneStates.forEach((_, i) => {
    if (genSceneStates[i].state !== 'error') updateGenScene(i, 'done', null);
  });

  const db = document.getElementById('download-box');
  if (db) db.style.display = 'block';
  const dl = document.getElementById('download-link');
  if (dl) dl.href = '/download/' + jobId;
  setStep(5);
  notify('🎉 Your video is ready!');
  clearSavedJob();
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTINUE SERIES
// ─────────────────────────────────────────────────────────────────────────────
function triggerUpload() {
  document.getElementById('video-upload').click();
}

async function handleVideoUpload(input) {
  const file = input.files[0];
  if (!file) return;

  const bar = document.getElementById('file-info-bar');
  const nameEl = document.getElementById('upload-filename');
  nameEl.textContent = file.name;
  bar.classList.add('visible');

  const btn = document.getElementById('analyze-btn');
  btn.innerHTML = '⏫ Uploading...';
  btn.disabled = true;

  try {
    const formData = new FormData();
    formData.append('video', file);
    const resp = await fetch('/upload_video', {method:'POST', body: formData});
    const data = await resp.json();
    uploadedVideoPath = data.path;
    notify('✅ Video uploaded: ' + file.name);
  } catch(e) {
    notify('Upload failed: ' + e, true);
  } finally {
    btn.innerHTML = '🔍 Analyze Video & Write Next Episode';
    btn.disabled = false;
  }
}

async function analyzeVideo() {
  if (!uploadedVideoPath) { notify('Please upload a video first!', true); return; }

  const btn = document.getElementById('analyze-btn');
  btn.disabled = true;
  btn.innerHTML = '🔍 Analyzing...';

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
    btn.innerHTML = '🔍 Analyze Video & Write Next Episode';
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
      <div class="char-desc" style="color:#555;margin-top:3px">Voice: ${c.voice_style}</div>
    </div>`).join('');

  document.getElementById('bible-display').innerHTML = `
    <div class="card-title">📖 ${bible.show_title || 'Show Bible'}</div>
    <div class="bible-section">
      <h3>Genre & Tone</h3>
      <p style="font-size:.83rem;color:#888">${bible.genre} · ${bible.tone} · ${bible.visual_style}</p>
    </div>
    <div class="bible-section">
      <h3>Story So Far</h3>
      <p style="font-size:.83rem;color:#888">${bible.episode_summary}</p>
    </div>
    <div class="bible-section">
      <h3>Characters Detected</h3>
      ${chars}
    </div>
    <div class="bible-section">
      <h3>Next Episode Hook</h3>
      <p style="font-size:.83rem;color:#888">${bible.next_episode_hook}</p>
    </div>`;
}

async function regenerateScript() {
  if (!showBible) return;
  const btn = document.querySelector('[onclick="regenerateScript()"]');
  btn.textContent = '⏳ Regenerating...';
  btn.disabled = true;
  try {
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
    notify('Script regenerated!');
  } catch(e) { notify('Regenerate failed: ' + e, true); }
  finally { btn.textContent = '🔄 Regenerate'; btn.disabled = false; }
}

function useGeneratedScript() {
  const script = document.getElementById('generated-script').value;
  document.getElementById('script_input').value = script;
  setMode('script');
  parseScript();
}

function backToUpload() {
  document.getElementById('view-bible').style.display = 'none';
  document.getElementById('view-upload').style.display = 'block';
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
  approvedScenes = [];
  genSceneStates = [];
  currentJobId = null;
  clearSavedJob();
  document.getElementById('view-generate').style.display = 'none';
  document.getElementById('download-box').style.display = 'none';
  document.getElementById('view-input').style.display = 'block';
  document.getElementById('log-output').textContent = 'Waiting to start...';
  document.getElementById('progress-fill').style.width = '0';
  document.getElementById('pulse-dot').style.background = 'var(--red)';
  setStep(1);
}

// ─────────────────────────────────────────────────────────────────────────────
// DRAG & DROP on upload zone
// ─────────────────────────────────────────────────────────────────────────────
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
        for s in scenes:
            s["_status"] = "pending"
        return jsonify({"scenes": scenes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generate", methods=["POST"])
def generate():
    """Start the full generation pipeline in a background thread."""
    data      = request.json
    scenes    = data.get("scenes", [])
    project   = data.get("project_name", "project")
    provider  = data.get("provider", "kling")
    fal_key   = data.get("fal_key", "")
    oai_key   = data.get("openai_key", "")
    bg_music  = data.get("bg_music", "")
    voice_map = data.get("voice_map", {})
    style     = data.get("style", "cinematic photorealistic")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "running", "logs": "Starting...\n",
        "scenes_done": 0, "output": None,
        "status_msg": "Initializing pipeline...",
        "scene_images": {}   # scene_number → local image path
    }

    # Force Kling if Fal.ai key is present
    active_fal_key = fal_key or os.environ.get("FAL_KEY", "")
    if active_fal_key and provider in ("demo", "", None):
        provider = "kling"

    def run():
        if fal_key:
            os.environ["FAL_KEY"]     = fal_key
            os.environ["FAL_API_KEY"] = fal_key
        if oai_key:
            os.environ["OPENAI_API_KEY"] = oai_key
        el_key = data.get("elevenlabs_key", "") or os.environ.get("ELEVENLABS_API_KEY", "")
        if el_key:
            os.environ["ELEVENLABS_API_KEY"] = el_key

        log_lines = []
        def log(msg):
            log_lines.append(msg)
            jobs[job_id]["logs"] = "\n".join(log_lines[-120:])

        try:
            import sys
            sys.path.insert(0, str(_BASE))
            from image_gen  import generate_image
            from tts_engine import generate_audio_for_scene, build_scene_audio_track
            from assembler  import process_scene, assemble_final_video
            from tool_router import plan_project_tools

            # ── Auto-select best tools for this project ──
            tool_plan = plan_project_tools(scenes, style=style, provider_override=provider)
            log(f"\n🤖 INTELLIGENT TOOL SELECTION")
            log(f"   OpenAI:      {tool_plan['api_status']['openai']}")
            log(f"   Fal.ai:      {tool_plan['api_status']['fal_ai']}")
            log(f"   ElevenLabs:  {tool_plan['api_status']['elevenlabs']}")
            log(f"   Strategy:    {tool_plan['overall_summary']}")
            if tool_plan['animation_breakdown']:
                breakdown = ', '.join(f"{k}: {v} scene(s)" for k,v in tool_plan['animation_breakdown'].items())
                log(f"   Animation:   {breakdown}")
            log("")
            jobs[job_id]["tool_plan"] = tool_plan

            # Use router's animation provider if user selected 'auto'
            effective_provider = provider
            if provider in ('auto', '', None):
                first_anim = tool_plan['scene_plans'][0]['animation'] if tool_plan['scene_plans'] else {}
                effective_provider = first_anim.get('provider_key', 'kling')
                log(f"   Auto-selected animation: {effective_provider}")

            clip_paths = []
            for i, scene in enumerate(scenes):
                sn    = scene.get("scene_number", i + 1)
                title = scene.get("title", f"Scene {sn}")
                log(f"[{sn}/{len(scenes)}] 🖼️  Generating image: {title}")
                jobs[job_id]["status_msg"] = f"Scene {sn}/{len(scenes)} — generating image..."

                # Image
                try:
                    img_path = generate_image(scene, project, style=style)
                    scene["_image_path"] = img_path
                    jobs[job_id]["scene_images"][str(sn)] = img_path
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
                    clip = process_scene(scene, project, effective_provider, add_captions=True)
                    clip_paths.append(clip)
                    jobs[job_id]["scenes_done"] = i + 1
                    log(f"[{sn}/{len(scenes)}] ✅ Scene complete → {clip}")
                except Exception as e:
                    log(f"[{sn}/{len(scenes)}] ❌ Animation failed: {e}")

            if not clip_paths:
                raise ValueError("No clips were generated")

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


@app.route("/tool_plan", methods=["POST"])
def tool_plan_endpoint():
    """Return the intelligent tool plan for a set of scenes before generation."""
    data   = request.json or {}
    scenes = data.get("scenes", [])
    style  = data.get("style", "cinematic photorealistic")
    provider = data.get("provider", "auto")
    fal_key = data.get("fal_key", "")
    oai_key = data.get("openai_key", "")
    if fal_key: os.environ["FAL_KEY"] = fal_key
    if oai_key: os.environ["OPENAI_API_KEY"] = oai_key
    try:
        from tool_router import plan_project_tools
        plan = plan_project_tools(scenes, style=style, provider_override=provider)
        return jsonify(plan)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/scene_image/<job_id>/<int:scene_num>")
def scene_image(job_id, scene_num):
    """Return the URL for a scene's generated image (for live preview)."""
    job = jobs.get(job_id, {})
    img_path = job.get("scene_images", {}).get(str(scene_num))
    if img_path and Path(img_path).exists():
        return jsonify({"url": f"/serve_image/{job_id}/{scene_num}"})
    return jsonify({"url": None}), 404


@app.route("/serve_image/<job_id>/<int:scene_num>")
def serve_image(job_id, scene_num):
    """Serve a scene image file directly."""
    job = jobs.get(job_id, {})
    img_path = job.get("scene_images", {}).get(str(scene_num))
    if img_path and Path(img_path).exists():
        return send_file(img_path, mimetype="image/png")
    return "Not found", 404


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
    # Overwrite any existing file with same name (allows "replace video")
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
        sys.path.insert(0, str(_BASE))
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
        sys.path.insert(0, str(_BASE))
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
