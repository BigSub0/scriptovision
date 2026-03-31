# ScriptoVision — Complete Script-to-Video Production App

**Built for Sub / Better Business Solutions AI**

ScriptoVision turns your scripts, stories, and existing episodes into fully produced videos — with AI-generated images, animated scenes, voiceovers, dialogue, and a final assembled MP4.

---

## Two Modes

### ✍️ Script Mode
Paste any script or story → AI breaks it into scenes → **You approve every scene** → Generate images, audio, animation, and final video.

### 📺 Continue Series Mode
Upload an existing episode of 4AllBuddies, Trap Daddy Series, or any show → AI analyzes the characters, style, and story → Writes the next episode → You review and produce it.

---

## How to Run

### Requirements
- Python 3.9+
- FFmpeg (install: `sudo apt install ffmpeg` or `brew install ffmpeg`)
- Internet connection (for gTTS audio fallback)

### Install & Start
```bash
cd scriptovision
pip install flask requests openai gtts pillow
python app.py
```

Then open: **http://localhost:8080**

---

## The 5-Step Workflow (Script Mode)

| Step | What Happens |
| :--- | :--- |
| **1. Input** | Paste your full script or story |
| **2. Review** | AI breaks it into scenes — you see every scene card |
| **3. Approve** | Approve, edit, reorder, or remove scenes before anything is generated |
| **4. Generate** | Images → Audio → Animation → Assembly runs automatically |
| **5. Done** | Download your finished MP4 |

> **You are in full control.** Nothing is generated until you click Approve.

---

## API Keys (Optional — Demo Mode Works Without Them)

| Key | What It Unlocks | Where to Get It |
| :--- | :--- | :--- |
| **OpenAI API Key** | GPT scene parsing, DALL-E images, OpenAI TTS voices | [platform.openai.com](https://platform.openai.com) |
| **Fal.ai API Key** | Real AI video animation (LTX-2, Wan 2.5, Kling) | [fal.ai](https://fal.ai) |

**Without API keys:** The app runs in Demo Mode — Ken Burns zoom effects on placeholder images, Google TTS audio, full scene approval workflow. Everything works, just with placeholder visuals.

---

## Animation Providers

| Provider | Quality | Cost | Notes |
| :--- | :--- | :--- | :--- |
| **Demo Mode** | Placeholder | Free | Ken Burns zoom, gTTS audio |
| **LTX-2** | High + Audio | ~$0.05/clip | Best for synchronized audio+video |
| **Wan 2.5** | Very High | ~$0.10/clip | Excellent motion quality |
| **Kling Pro** | Cinematic | ~$0.20/clip | Best overall quality |

---

## Continue Series Mode

1. Click **📺 Continue Series** tab
2. Upload any episode (MP4, MOV, AVI)
3. Optionally add a show title and creative direction
4. Click **Analyze Video & Write Next Episode**
5. The AI will detect:
   - All characters and their voices/personalities
   - Visual style and tone
   - Story arc and cliffhanger
   - Recurring locations
6. It writes a complete script for the next episode
7. You can edit the script or regenerate it
8. Click **Use This Script → Review Scenes** to produce it

---

## Voice Assignments

The app automatically assigns voices to each character:
- **Narrator** → `onyx` (deep, authoritative)
- **Male characters** → `echo`
- **Female characters** → `nova`
- **Default** → `alloy`

You can override any character's voice in the sidebar before generating.

---

## File Structure

```
scriptovision/
├── app.py              ← Main Flask app + Web UI
├── scene_parser.py     ← Script → scenes (GPT or demo)
├── image_gen.py        ← Scene images (DALL-E or placeholder)
├── tts_engine.py       ← Voiceover + dialogue audio
├── assembler.py        ← Animation + FFmpeg assembly
├── video_analyzer.py   ← Video analysis + series continuation
├── output/             ← Final videos saved here
├── temp/               ← Intermediate clips
├── audio/              ← Generated audio files
└── images/             ← Generated scene images
```

---

## Restart Anytime

```bash
cd scriptovision
python app.py
```

Open **http://localhost:8080** in your browser.

---

*ScriptoVision — Built by Manus for Better Business Solutions AI*
