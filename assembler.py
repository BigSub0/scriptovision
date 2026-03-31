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

_BASE     = Path(os.environ.get("BASE_DIR", "/home/ubuntu/scriptovision"))
TEMP_DIR   = _BASE / "temp"
OUTPUT_DIR = _BASE / "output"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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
    """Upload a local image to Fal.ai storage and return the public URL."""
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    # Determine content type
    ext = Path(image_path).suffix.lower()
    content_type = "image/png" if ext == ".png" else "image/jpeg"

    init_resp = requests.post(
        "https://rest.alpha.fal.ai/storage/upload/initiate",
        headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
        json={"content_type": content_type, "file_name": Path(image_path).name},
        timeout=15
    )
    init_resp.raise_for_status()
    data = init_resp.json()
    file_url = data["file_url"]
    upload_url = data["upload_url"]

    # PUT the image bytes
    put_resp = requests.put(
        upload_url,
        data=img_bytes,
        headers={"Content-Type": content_type},
        timeout=60
    )
    put_resp.raise_for_status()
    return file_url


def _fal_submit_job(model_id: str, payload: dict, fal_key: str) -> str:
    """Submit a job to the Fal.ai async queue. Returns request_id."""
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
    return req_id


def _fal_poll_job(model_id: str, request_id: str, fal_key: str,
                  max_wait: int = 300, poll_interval: int = 10) -> dict:
    """Poll the Fal.ai queue until the job completes. Returns result dict."""
    # Extract base model name (strip version suffix for queue URLs)
    base = model_id.split("/")[0] + "/" + model_id.split("/")[1]
    status_url = f"{FAL_QUEUE_BASE}/{model_id}/requests/{request_id}/status"
    result_url = f"{FAL_QUEUE_BASE}/{model_id}/requests/{request_id}"
    headers = {"Authorization": f"Key {fal_key}"}

    elapsed = 0
    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        r = requests.get(status_url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "UNKNOWN")

        if status == "COMPLETED":
            result = requests.get(result_url, headers=headers, timeout=15)
            result.raise_for_status()
            return result.json()
        elif status in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Fal.ai job {request_id} {status}: {data}")
        # IN_QUEUE or IN_PROGRESS — keep polling

    raise TimeoutError(f"Fal.ai job {request_id} did not complete in {max_wait}s")


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
                  project_name: str, provider: str = "kling") -> str:
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
    out_path  = str(TEMP_DIR / f"{project_name}_clip_{scene_num:02d}.mp4")

    if Path(out_path).exists():
        return out_path

    fal_key = os.environ.get("FAL_KEY", os.environ.get("FAL_API_KEY", ""))

    if fal_key and provider != "demo":
        try:
            return _kling_animate(
                image_path=image_path,
                motion_prompt=motion,
                duration=kling_duration,
                audio_path=audio_path,
                out_path=out_path,
                fal_key=fal_key,
                provider=provider
            )
        except Exception as e:
            print(f"  ⚠️  AI animation failed ({e}), using Ken Burns fallback")
            return _ken_burns_fallback(scene, image_path, audio_path, duration, out_path)
    else:
        return _ken_burns_fallback(scene, image_path, audio_path, duration, out_path)


def _kling_animate(image_path: str, motion_prompt: str, duration: str,
                   audio_path: str, out_path: str,
                   fal_key: str, provider: str = "kling") -> str:
    """
    Full Kling 1.6 image-to-video animation via Fal.ai async queue.
    """
    model_id = MODEL_MAP.get(provider, MODEL_MAP[DEFAULT_MODEL])

    # Step 1: Upload image
    print(f"    📤 Uploading image to Fal.ai...")
    image_url = _fal_upload_image(image_path, fal_key)

    # Step 2: Build payload (Kling-specific params)
    payload = {
        "image_url": image_url,
        "prompt": motion_prompt,
        "negative_prompt": "static image, no motion, slideshow, zoom only, blurry, low quality",
        "duration": duration,
        "aspect_ratio": "16:9",
        "cfg_scale": 0.5
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
    request_id = _fal_submit_job(model_id, payload, fal_key)
    print(f"    ⏳ Job {request_id[:8]}... queued, waiting for completion...")

    # Step 4: Poll until done
    result = _fal_poll_job(model_id, request_id, fal_key,
                           max_wait=360, poll_interval=12)

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
# SUBTITLE OVERLAY
# ─────────────────────────────────────────────────────────────────────────────

def add_subtitles_to_clip(clip_path: str, scene: dict, out_path: str) -> str:
    """Burn dialogue subtitles into the video clip."""
    dialogue  = scene.get("dialogue", [])
    voiceover = scene.get("voiceover", "")
    duration  = scene.get("duration", 6)

    if not dialogue and not voiceover:
        shutil.copy(clip_path, out_path)
        return out_path

    lines = []
    if voiceover:
        lines.append(voiceover[:80])
    for d in dialogue[:2]:
        lines.append(f"{d.get('speaker','')}: {d.get('line','')}"[:80])

    def safe(t):
        return t.replace("'", "").replace(":", " -").replace("%", "").replace("\\", "")

    vf_parts = []
    y_positions = [580, 620, 650]
    for i, line in enumerate(lines[:3]):
        y = y_positions[min(i, len(y_positions) - 1)]
        vf_parts.append(
            f"drawtext=text='{safe(line)}':fontsize=20:fontcolor=white:"
            f"x=(w-text_w)/2:y={y}:box=1:boxcolor=black@0.6:boxborderw=5"
        )

    vf = ",".join(vf_parts)
    cmd = ["ffmpeg", "-y", "-i", clip_path, "-vf", vf,
           "-c:v", "libx264", "-c:a", "copy", out_path]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
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

    # Concatenate
    concat_path = TEMP_DIR / f"{project_name}_concat.mp4"
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
                  add_captions: bool = True) -> str:
    """
    Full pipeline for one scene:
    image + audio → AI animated clip → add captions → return clip path
    """
    image_path = scene.get("_image_path", "")
    audio_path = scene.get("_audio_path", "")

    clip_path = animate_scene(scene, image_path, audio_path,
                              project_name, provider)

    if add_captions:
        captioned_path = clip_path.replace(".mp4", "_cap.mp4")
        clip_path = add_subtitles_to_clip(clip_path, scene, captioned_path)

    return clip_path
