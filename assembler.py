"""
ScriptoVision — Animation & Final Assembly Pipeline
Uses Kling 1.6 (via Fal.ai async queue) for real cinematic image-to-video.
Ken Burns is ONLY used as an emergency fallback if the API is unavailable.
"""

import os
import json
import time
import subprocess
import requests
import shutil
from pathlib import Path

_BASE = Path(os.environ.get("BASE_DIR", "/home/ubuntu/scriptovision"))

def _resolve_dir(env_key: str, default_subdir: str) -> Path:
    """Use env var path if writable (disk mounted), else fall back to _BASE/subdir."""
    env_val = os.environ.get(env_key, "")
    if env_val:
        p = Path(env_val)
        if p.parent.exists() or p.exists():
            try:
                p.mkdir(parents=True, exist_ok=True)
                test = p / ".write_test"
                test.write_text("ok")
                test.unlink()
                return p
            except Exception:
                pass
    fallback = _BASE / default_subdir
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback

TEMP_DIR   = _resolve_dir("TEMP_DIR",   "temp")
OUTPUT_DIR = _resolve_dir("OUTPUT_DIR", "output")

FAL_QUEUE_BASE = "https://queue.fal.run"

# Model endpoints — all use async queue
MODEL_MAP = {
    "kling":  "fal-ai/kling-video/v1.6/standard/image-to-video",
    "kling_pro": "fal-ai/kling-video/v1.6/pro/image-to-video",
    "ltx2":   "fal-ai/ltx-video/image-to-video",
    "wan25":  "fal-ai/wan-video/image-to-video",
    "wan21":  "fal-ai/wan-video/v2.1/image-to-video",
}
DEFAULT_MODEL = "kling"


# ─────────────────────────────────────────────────────────────────────────────
# FAL.AI ASYNC QUEUE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _fal_upload_image(image_path: str, fal_key: str) -> str:
    """
    Upload a local image to Fal.ai CDN and return the public URL.
    Uses the official fal_client SDK (handles auth, retries, fallback endpoints).
    Falls back to base64 data URI if SDK upload fails.
    """
    import base64

    ext = Path(image_path).suffix.lower()
    content_type = "image/png" if ext == ".png" else "image/jpeg"

    # Method 1: Use official fal_client SDK (recommended by Fal.ai docs)
    try:
        import fal_client
        os.environ["FAL_KEY"] = fal_key
        url = fal_client.upload_file(image_path)
        print(f"    ✅ Uploaded via fal_client SDK: {url[:60]}...")
        return url
    except Exception as e:
        print(f"    ⚠️  fal_client upload failed ({e}), trying data URI fallback...")

    # Method 2: Base64 data URI (works with all Fal.ai models, no upload needed)
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        data_uri = f"data:{content_type};base64,{b64}"
        print(f"    ✅ Using base64 data URI ({len(data_uri)//1024}KB)")
        return data_uri
    except Exception as e:
        raise RuntimeError(f"All image upload methods failed: {e}")


def _fal_submit_job(model_id: str, payload: dict, fal_key: str) -> dict:
    """Submit a job to the Fal.ai async queue.
    Returns dict with request_id, status_url, and response_url
    exactly as provided by Fal.ai (do NOT reconstruct these URLs manually).
    """
    url = f"{FAL_QUEUE_BASE}/{model_id}"
    resp = requests.post(
        url,
        headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    req_id = data.get("request_id")
    if not req_id:
        raise ValueError(f"No request_id in response: {data}")
    return {
        "request_id": req_id,
        "status_url": data.get("status_url"),      # Use Fal.ai's own status URL
        "response_url": data.get("response_url"),  # Use Fal.ai's own result URL
    }


def _fal_poll_job(status_url: str, response_url: str, request_id: str, fal_key: str,
                  max_wait: int = 600, poll_interval: int = 12) -> dict:
    """Poll the Fal.ai queue until the job completes. Returns result dict.
    Uses the status_url and response_url returned by Fal.ai at submit time.
    Timeout extended to 600s (10 min) to handle peak-hour queue delays.
    """
    headers = {"Authorization": f"Key {fal_key}"}

    elapsed = 0
    consecutive_errors = 0
    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        try:
            r = requests.get(status_url, headers=headers, timeout=30)
            r.raise_for_status()
            consecutive_errors = 0  # reset on success
        except requests.exceptions.RequestException as e:
            consecutive_errors += 1
            print(f"    ⚠️  Poll error #{consecutive_errors} (retrying): {e}")
            if consecutive_errors >= 5:
                raise RuntimeError(f"Fal.ai polling failed after 5 consecutive errors: {e}")
            continue

        data = r.json()
        status = data.get("status", "UNKNOWN")
        queue_pos = data.get("queue_position", "")
        pos_str = f" | queue pos: {queue_pos}" if queue_pos else ""
        print(f"    ⏳ Job status: {status} ({elapsed}s elapsed){pos_str}")

        if status == "COMPLETED":
            result = requests.get(response_url, headers=headers, timeout=30)
            result.raise_for_status()
            return result.json()
        elif status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Fal.ai job {request_id} {status}: {data}")
        # IN_QUEUE or IN_PROGRESS — keep polling

    raise TimeoutError(f"Fal.ai job {request_id} did not complete in {max_wait}s — try again during off-peak hours")


def _fal_download_video(video_url: str, out_path: str) -> str:
    """Download the generated video to a local path."""
    r = requests.get(video_url, timeout=120, stream=True)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ANIMATION FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def animate_scene(scene: dict, image_path: str, audio_path: str,
                  project_name: str, provider: str = "kling",
                  visual_style: str = "cinematic photorealistic") -> str:
    """
    Animate a scene image into a cinematic video clip with audio.
    Uses Kling 1.6 (or chosen model) via Fal.ai async queue.
    Falls back to Ken Burns ONLY if no API key is available.
    Returns path to the output MP4 clip.
    """
    scene_num = scene.get("scene_number", 1)
    duration  = int(scene.get("duration", 5))
    # Kling supports 5 or 10 seconds
    kling_duration = "10" if duration >= 8 else "5"
    motion    = scene.get("motion_prompt", "Cinematic camera movement, natural motion, film quality.")

    # Inject live-action motion prefix for cinematic/photorealistic styles
    live_action_styles = {"cinematic photorealistic", "dark gritty noir", "urban street photography"}
    if visual_style in live_action_styles:
        motion = (
            "Realistic human movement, natural body language, cinematic camera work, "
            "photorealistic motion, no cartoon motion, no animation artifacts, "
            "film-quality movement. " + motion
        )

    out_path  = str(TEMP_DIR / f"{project_name}_clip_{scene_num:02d}.mp4")

    if Path(out_path).exists():
        return out_path

    fal_key = os.environ.get("FAL_KEY", os.environ.get("FAL_API_KEY", ""))

    # ── Guard: if image failed to generate, create a placeholder so animation never crashes ──
    if not image_path or not Path(image_path).exists():
        print(f"  ⚠️  Image missing for scene {scene_num} — generating placeholder so animation can continue...")
        try:
            from image_gen import _placeholder_generate
            placeholder_path = str(TEMP_DIR / f"{project_name}_placeholder_{scene_num:02d}.png")
            image_path = _placeholder_generate(scene, placeholder_path)
            scene["_image_path"] = image_path
        except Exception as pe:
            print(f"  ❌  Placeholder generation failed: {pe} — skipping animation")
            # Create a minimal black frame as absolute last resort
            import subprocess as _sp
            _sp.run([
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"color=black:size=1280x720:duration={duration}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path
            ], capture_output=True)
            return out_path

    if fal_key and provider != "demo":
        # Try Kling first, then Minimax as fallback if balance exhausted or 403
        try:
            return _kling_animate(
                image_path=image_path,
                motion_prompt=motion,
                duration=kling_duration,
                audio_path=audio_path,
                out_path=out_path,
                fal_key=fal_key,
                provider=provider,
                visual_style=visual_style
            )
        except Exception as e:
            err_str = str(e)
            # Detect balance exhaustion or auth issues — try Minimax as fallback
            if "403" in err_str or "Exhausted balance" in err_str or "locked" in err_str or "Forbidden" in err_str:
                print(f"  ⚠️  Fal.ai Kling failed (403/balance): {err_str[:80]}")
                print(f"  🔄 Switching to Minimax animation as fallback...")
                try:
                    return _minimax_animate(
                        image_path=image_path,
                        motion_prompt=motion,
                        audio_path=audio_path,
                        out_path=out_path,
                        fal_key=fal_key,
                        duration=int(kling_duration)
                    )
                except Exception as me:
                    print(f"  ⚠️  Minimax also failed: {me}")
                    print(f"  🔄 Using Ken Burns as last resort...")
                    return _ken_burns_fallback(scene, image_path, audio_path, duration, out_path)
            else:
                raise  # Re-raise non-balance errors
    else:
        # Only use Ken Burns if explicitly in demo mode (no API key)
        print(f"  ⚠️  No Fal.ai key found — using demo mode. Add your Fal.ai key for real AI animation.")
        return _ken_burns_fallback(scene, image_path, audio_path, duration, out_path)


def _kling_animate(image_path: str, motion_prompt: str, duration: str,
                   audio_path: str, out_path: str,
                   fal_key: str, provider: str = "kling",
                   visual_style: str = "cinematic photorealistic") -> str:
    """
    Full Kling 1.6 image-to-video animation via Fal.ai async queue.
    """
    model_id = MODEL_MAP.get(provider, MODEL_MAP[DEFAULT_MODEL])

    # Step 1: Upload image
    print(f"    📤 Uploading image to Fal.ai...")
    image_url = _fal_upload_image(image_path, fal_key)

    # cfg_scale: higher = more faithful to prompt/image, less creative drift
    # For live-action/cinematic: 0.8 keeps it photorealistic
    # For animated/cartoon styles: 0.5 allows more stylistic freedom
    live_action_styles = {"cinematic photorealistic", "dark gritty noir", "urban street photography"}
    cfg = 0.8 if visual_style in live_action_styles else 0.5

    # Negative prompt — stronger for live-action to prevent cartoon artifacts
    if visual_style in live_action_styles:
        neg_prompt = (
            "cartoon, anime, animation, illustrated, drawn, painted, CGI, 3D render, "
            "static image, no motion, slideshow, zoom only, blurry, low quality, "
            "unnatural movement, morphing, melting, distortion"
        )
    else:
        neg_prompt = "static image, no motion, slideshow, zoom only, blurry, low quality"

    # Step 2: Build payload (Kling-specific params)
    payload = {
        "image_url": image_url,
        "prompt": motion_prompt,
        "negative_prompt": neg_prompt,
        "duration": duration,
        "aspect_ratio": "16:9",
        "cfg_scale": cfg
    }

    # LTX-2 / Wan use different params
    if "ltx" in model_id or "wan" in model_id:
        payload = {
            "image_url": image_url,
            "prompt": motion_prompt,
            "negative_prompt": "static, no motion, blurry",
            "num_frames": 97,
            "fps": 24,
            "guidance_scale": 3.0,
            "num_inference_steps": 40
        }

    # Step 3: Submit job
    print(f"    🎬 Submitting to {model_id}...")
    job = _fal_submit_job(model_id, payload, fal_key)
    request_id = job["request_id"]
    status_url = job["status_url"]
    response_url = job["response_url"]
    print(f"    ⏳ Job {request_id[:8]}... queued")
    print(f"    📡 Status URL: {status_url}")

    # Step 4: Poll until done (using Fal.ai's own URLs — not reconstructed)
    result = _fal_poll_job(status_url, response_url, request_id, fal_key,
                           max_wait=600, poll_interval=12)

    # Step 5: Extract video URL
    video_url = (
        result.get("video", {}).get("url") or
        result.get("url") or
        (result.get("videos") or [{}])[0].get("url")
    )
    if not video_url:
        raise ValueError(f"No video URL in result: {list(result.keys())}")

    print(f"    ✅ AI animation complete! Downloading...")

    # Step 6: Download raw video
    raw_path = out_path.replace(".mp4", "_raw.mp4")
    _fal_download_video(video_url, raw_path)

    # Step 7: Mix in audio
    _mix_audio(raw_path, audio_path, out_path, int(duration) if duration.isdigit() else 5)
    Path(raw_path).unlink(missing_ok=True)
    return out_path


def _minimax_animate(image_path: str, motion_prompt: str, audio_path: str,
                     out_path: str, fal_key: str, duration: int = 5) -> str:
    """
    Minimax image-to-video animation via Fal.ai as fallback when Kling is unavailable.
    Uses fal-ai/minimax-video model.
    """
    import os, requests
    model_id = "fal-ai/minimax-video/image-to-video"
    print(f"    📤 Uploading image for Minimax...")
    image_url = _fal_upload_image(image_path, fal_key)

    payload = {
        "image_url": image_url,
        "prompt": motion_prompt,
        "prompt_optimizer": True
    }

    print(f"    🎬 Submitting to Minimax...")
    job = _fal_submit_job(model_id, payload, fal_key)
    request_id = job["request_id"]
    status_url  = job["status_url"]
    response_url = job["response_url"]
    print(f"    ⏳ Minimax job {request_id[:8]}... queued")

    result = _fal_poll_job(status_url, response_url, request_id, fal_key,
                           max_wait=600, poll_interval=15)

    video_url = (
        result.get("video", {}).get("url") or
        result.get("url") or
        (result.get("videos") or [{}])[0].get("url")
    )
    if not video_url:
        raise ValueError(f"No video URL in Minimax result: {list(result.keys())}")

    print(f"    ✅ Minimax animation complete! Downloading...")
    raw_path = out_path.replace(".mp4", "_raw.mp4")
    _fal_download_video(video_url, raw_path)
    _mix_audio(raw_path, audio_path, out_path, duration)
    Path(raw_path).unlink(missing_ok=True)
    return out_path


def _ken_burns_fallback(scene: dict, image_path: str, audio_path: str,
                        duration: int, out_path: str) -> str:
    """
    FALLBACK ONLY: Ken Burns zoom/pan effect when no API key is available.
    This is NOT the primary animation method.
    """
    scene_num = scene.get("scene_number", 1)
    fps = 24
    total_frames = duration * fps
    raw_clip = out_path.replace(".mp4", "_raw.mp4")

    zoom_styles = [
        f"zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:fps={fps}:s=1280x720",
        f"zoompan=z='if(lte(zoom,1.0),1.5,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:fps={fps}:s=1280x720",
        f"zoompan=z='min(zoom+0.001,1.3)':x='0':y='0':d={total_frames}:fps={fps}:s=1280x720",
        f"zoompan=z='min(zoom+0.001,1.3)':x='iw-iw/zoom':y='ih-ih/zoom':d={total_frames}:fps={fps}:s=1280x720",
    ]
    zoom_filter = zoom_styles[scene_num % len(zoom_styles)]

    if image_path and Path(image_path).exists():
        vf = (
            f"scale=1280:720:force_original_aspect_ratio=increase,"
            f"crop=1280:720,{zoom_filter},setsar=1"
        )
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", image_path,
               "-vf", vf, "-t", str(duration),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", raw_clip]
    else:
        title = scene.get("title", f"Scene {scene_num}")
        colors = ["0x1a1a2e", "0x16213e", "0x0f3460", "0x533483", "0x1a0a2e"]
        color = colors[scene_num % len(colors)]
        safe_title = title[:40].replace("'", "").replace(":", "-")
        cmd = ["ffmpeg", "-y",
               "-f", "lavfi", "-i", f"color=c={color}:size=1280x720:duration={duration}:rate={fps}",
               "-vf", f"drawtext=text='{safe_title}':fontsize=36:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", raw_clip]

    subprocess.run(cmd, capture_output=True, check=True)
    _mix_audio(raw_clip, audio_path, out_path, duration)
    Path(raw_clip).unlink(missing_ok=True)
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# AUDIO MIXING
# ─────────────────────────────────────────────────────────────────────────────

def _mix_audio(video_path: str, audio_path: str, out_path: str, duration: int):
    """Mix audio track into video clip."""
    if audio_path and Path(audio_path).exists():
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac",
            "-shortest", "-t", str(duration + 2),
            out_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac",
            "-shortest", "-t", str(duration),
            out_path
        ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        # If audio mix fails, just copy the video
        shutil.copy(video_path, out_path)


# ─────────────────────────────────────────────────────────────────────────────
# LIP SYNC (Kling LipSync via Fal.ai)
# ─────────────────────────────────────────────────────────────────────────────

def apply_lipsync(clip_path: str, audio_path: str, scene: dict,
                 project_name: str, fal_key: str) -> str:
    """
    Apply Kling LipSync to a scene clip that has dialogue.
    Takes the animated clip + audio and returns a lip-synced version.
    Only runs on scenes with actual character dialogue (not voiceover-only scenes).
    Cost: $0.014 per 5s increment.
    """
    dialogue = scene.get("dialogue", [])
    if not dialogue:
        # No character dialogue — skip lip sync (voiceover scenes don't need it)
        return clip_path

    if not audio_path or not Path(audio_path).exists():
        print(f"    ⚠️  No audio for lip sync — skipping")
        return clip_path

    if not fal_key:
        print(f"    ⚠️  No Fal.ai key — skipping lip sync")
        return clip_path

    scene_num = scene.get("scene_number", 1)
    lipsync_path = str(TEMP_DIR / f"{project_name}_clip_{scene_num:02d}_lip.mp4")

    if Path(lipsync_path).exists():
        return lipsync_path

    print(f"    👄 Applying Kling LipSync to scene {scene_num}...")

    try:
        print(f"    📤 Uploading clip to Fal.ai for lip sync...")
        # Upload clip and audio to Fal.ai CDN
        video_url = _fal_upload_image(clip_path, fal_key)
        audio_url = _fal_upload_image(audio_path, fal_key)
        print(f"    📤 Both files uploaded. Submitting lip sync job...")

        # Submit lip sync job
        payload = {
            "video_url": video_url,
            "audio_url": audio_url,
        }
        job = _fal_submit_job("fal-ai/kling-video/lipsync/audio-to-video", payload, fal_key)
        print(f"    ⏳ LipSync job submitted: {job['request_id']}")
        print(f"    📶 Status URL: {job.get('status_url', 'N/A')}")
        print(f"    ⏳ Polling for result (lip sync takes 10-15 min)...")

        # Poll for result
        result = _fal_poll_job(
            status_url=job["status_url"],
            response_url=job["response_url"],
            request_id=job["request_id"],
            fal_key=fal_key,
            max_wait=1200,  # 20 min max
            poll_interval=20
        )

        # Extract video URL from result — handle multiple response shapes
        video_data = result.get("video", {})
        lipsync_url = None
        if isinstance(video_data, dict):
            lipsync_url = video_data.get("url")
        elif isinstance(video_data, str):
            lipsync_url = video_data
        if not lipsync_url:
            # Try alternate keys
            lipsync_url = result.get("url") or result.get("video_url")
        if not lipsync_url:
            raise ValueError(f"No video URL in lip sync result. Keys: {list(result.keys())}")

        print(f"    ⬇️  Downloading lip-synced clip...")
        _fal_download_video(lipsync_url, lipsync_path)
        print(f"    ✅ LipSync complete → {lipsync_path}")
        return lipsync_path

    except Exception as e:
        print(f"    ⚠️  LipSync FAILED: {e}")
        print(f"    ⚠️  Falling back to animated clip without lip sync")
        return clip_path  # Graceful fallback — never crash the pipeline


# ─────────────────────────────────────────────────────────────────────────────
# SUBTITLE OVERLAY (kept for reference but DISABLED — user does not want subtitles)
# ─────────────────────────────────────────────────────────────────────────────

def add_subtitles_to_clip(clip_path: str, scene: dict, out_path: str) -> str:
    """Burn clean, properly wrapped subtitles into the video clip."""
    dialogue  = scene.get("dialogue", [])
    voiceover = scene.get("voiceover", "")
    duration  = scene.get("duration", 6)

    if not dialogue and not voiceover:
        shutil.copy(clip_path, out_path)
        return out_path

    def wrap_text(text: str, max_chars: int = 48) -> list:
        """Wrap text into lines of max_chars, breaking at word boundaries."""
        words = text.split()
        lines, current = [], ""
        for word in words:
            if len(current) + len(word) + 1 <= max_chars:
                current = (current + " " + word).strip()
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:2]  # max 2 lines per subtitle block

    def safe(t: str) -> str:
        """Escape text for ffmpeg drawtext filter."""
        return (t.replace("'", "")
                 .replace("\\", "")
                 .replace(":", " ")
                 .replace("%", "pct")
                 .replace("[", "")
                 .replace("]", "")
                 .replace("(", "")
                 .replace(")", ""))

    # Build subtitle blocks — voiceover first, then dialogue (no speaker labels)
    subtitle_lines = []
    if voiceover:
        subtitle_lines.extend(wrap_text(voiceover.strip()))
    elif dialogue:
        # Use first dialogue line only, strip speaker name
        first_line = dialogue[0].get("line", "").strip()
        subtitle_lines.extend(wrap_text(first_line))

    if not subtitle_lines:
        shutil.copy(clip_path, out_path)
        return out_path

    # Position subtitles at bottom with proper spacing
    # For 720p: bottom bar at ~660, lines at 620 and 645
    vf_parts = []
    base_y = 630 if len(subtitle_lines) == 1 else 610
    line_spacing = 32

    for i, line in enumerate(subtitle_lines):
        y = base_y + (i * line_spacing)
        safe_line = safe(line)
        vf_parts.append(
            f"drawtext=text='{safe_line}'"
            f":fontsize=22:fontcolor=white:font=DejaVu Sans Bold"
            f":x=(w-text_w)/2:y={y}"
            f":box=1:boxcolor=black@0.7:boxborderw=8"
        )

    vf = ",".join(vf_parts)
    cmd = ["ffmpeg", "-y", "-i", clip_path, "-vf", vf,
           "-c:v", "libx264", "-preset", "fast", "-c:a", "copy", out_path]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        # Fallback: copy without subtitles rather than crash
        print(f"  ⚠️  Subtitle burn failed: {result.stderr.decode()[:200]}")
        shutil.copy(clip_path, out_path)
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# FINAL ASSEMBLY
# ─────────────────────────────────────────────────────────────────────────────

def assemble_final_video(clip_paths: list, project_name: str,
                         bg_music_path: str = None,
                         music_volume: float = 0.08) -> str:
    """Concatenate all scene clips into the final video."""
    from datetime import datetime
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_path = OUTPUT_DIR / f"{project_name}_{timestamp}.mp4"

    if not clip_paths:
        raise ValueError("No clips to assemble")

    # Filter to only valid clips
    valid_clips = [p for p in clip_paths if p and Path(p).exists() and Path(p).stat().st_size > 10000]
    if not valid_clips:
        raise ValueError("No valid clips found")

    if len(valid_clips) == 1:
        shutil.copy(valid_clips[0], str(final_path))
        return str(final_path)

    # Re-encode each clip to ensure uniform codec/resolution before concat
    normalized = []
    for i, clip in enumerate(valid_clips):
        norm_path = str(TEMP_DIR / f"{project_name}_norm_{i:02d}.mp4")
        result = subprocess.run([
            "ffmpeg", "-y", "-i", clip,
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "-r", "24", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            norm_path
        ], capture_output=True)
        if result.returncode == 0:
            normalized.append(norm_path)
        else:
            normalized.append(clip)

    # Write concat list
    list_file = TEMP_DIR / f"{project_name}_concat.txt"
    with open(list_file, "w") as f:
        for p in normalized:
            f.write(f"file '{p}'\n")

    # Concatenate with crossfade transitions between clips
    concat_path = TEMP_DIR / f"{project_name}_concat.mp4"
    if len(normalized) == 1:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart",
            str(concat_path)
        ], capture_output=True, check=True)
    else:
        # Build xfade filter chain for smooth crossfades
        # Each clip is ~5-10s, crossfade at 0.5s
        fade_dur = 0.4
        try:
            # Get durations of each clip
            durations = []
            for clip in normalized:
                r = subprocess.run([
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", clip
                ], capture_output=True, text=True)
                try:
                    durations.append(float(r.stdout.strip()))
                except Exception:
                    durations.append(6.0)

            # Build xfade + acrossfade filter complex
            inputs = []
            for clip in normalized:
                inputs += ["-i", clip]

            # Build video xfade chain
            vf_parts = []
            af_parts = []
            offset = 0.0
            prev_v = "[0:v]"
            prev_a = "[0:a]"

            for i in range(1, len(normalized)):
                offset += durations[i - 1] - fade_dur
                out_v = f"[v{i}]" if i < len(normalized) - 1 else "[vout]"
                out_a = f"[a{i}]" if i < len(normalized) - 1 else "[aout]"
                vf_parts.append(
                    f"{prev_v}[{i}:v]xfade=transition=fade:duration={fade_dur}:offset={offset:.3f}{out_v}"
                )
                af_parts.append(
                    f"{prev_a}[{i}:a]acrossfade=d={fade_dur}{out_a}"
                )
                prev_v = out_v
                prev_a = out_a

            filter_complex = ";".join(vf_parts + af_parts)

            cmd = ["ffmpeg", "-y"] + inputs + [
                "-filter_complex", filter_complex,
                "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-movflags", "+faststart",
                str(concat_path)
            ]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                raise RuntimeError("xfade failed, falling back to simple concat")
        except Exception as e:
            print(f"  ⚠️  Crossfade failed ({e}), using simple concat")
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_file),
                "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart",
                str(concat_path)
            ], capture_output=True, check=True)

    # Mix background music if provided
    if bg_music_path and Path(bg_music_path).exists():
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(concat_path),
            "-i", bg_music_path,
            "-filter_complex",
            f"[1:a]volume={music_volume},aloop=loop=-1:size=2e+09[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=3[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart",
            str(final_path)
        ], capture_output=True, check=True)
        concat_path.unlink(missing_ok=True)
    else:
        shutil.move(str(concat_path), str(final_path))

    list_file.unlink(missing_ok=True)
    # Clean up normalized clips
    for p in normalized:
        if "_norm_" in p:
            Path(p).unlink(missing_ok=True)

    return str(final_path)


# ─────────────────────────────────────────────────────────────────────────────
# FULL SCENE PROCESSING PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def process_scene(scene: dict, project_name: str,
                  provider: str = "kling",
                  add_captions: bool = False,
                  visual_style: str = "cinematic photorealistic") -> str:
    """
    Full pipeline for one scene:
    image + audio → AI animated clip → Kling LipSync (dialogue scenes only) → return clip
    Subtitles/captions are DISABLED — user does not want them.
    LipSync is applied automatically to any scene with character dialogue.
    """
    image_path = scene.get("_image_path", "")
    audio_path = scene.get("_audio_path", "")
    fal_key    = os.environ.get("FAL_KEY", os.environ.get("FAL_API_KEY", ""))

    # Step 1: Animate the scene image
    clip_path = animate_scene(scene, image_path, audio_path,
                              project_name, provider, visual_style=visual_style)

    # Step 2: Apply lip sync for dialogue scenes (graceful fallback if it fails)
    if fal_key and scene.get("dialogue"):
        clip_path = apply_lipsync(
            clip_path=clip_path,
            audio_path=audio_path,
            scene=scene,
            project_name=project_name,
            fal_key=fal_key
        )

    return clip_path
