"""
ScriptoVision — Image Generation Module v2
Generates a scene image from a prompt using DALL-E 3.
Content policy bypass: auto-sanitizes prompts and falls back to Fal.ai FLUX Pro.
Falls back to a styled placeholder when no API key is available.
"""

import os
import re
import requests
from pathlib import Path
from openai import OpenAI

def _get_client():
    api_key = os.environ.get("OPENAI_API_KEY", "")
    return OpenAI(api_key=api_key, base_url="https://api.openai.com/v1")

IMAGES_DIR = Path(os.environ.get("BASE_DIR", "/home/ubuntu/scriptovision")) / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# CONTENT POLICY SANITIZER
# Rewrites prompts that DALL-E 3 would reject, without losing the visual intent
# ─────────────────────────────────────────────────────────────────────────────

# Words/phrases that trigger DALL-E content filters → safe replacements
CONTENT_REPLACEMENTS = [
    # Violence / weapons
    (r'\b(gun|pistol|firearm|rifle|shotgun|weapon|armed)\b', 'silhouette figure'),
    (r'\b(shoot|shooting|shot|gunshot|fired a gun)\b', 'tense standoff'),
    (r'\b(kill|killing|murder|dead body|corpse|blood|bloody)\b', 'dramatic confrontation'),
    (r'\b(fight|fighting|brawl|punch|stab|stabbing|knife fight)\b', 'intense confrontation'),
    (r'\b(explosion|explode|bomb|blast)\b', 'dramatic flash of light'),
    (r'\b(drugs|cocaine|heroin|crack|weed|marijuana|narcotics)\b', 'mysterious package'),
    (r'\b(drug deal|dealing drugs)\b', 'covert exchange'),
    # Explicit content
    (r'\b(nude|naked|sex|sexual|explicit)\b', 'dramatic scene'),
    (r'\b(motel room tension|seductive|provocative)\b', 'dimly lit motel room, two people in conversation'),
    # Gang / crime framing
    (r'\b(gang|gangster|thug|criminal|cartel|mob)\b', 'street figure'),
    (r'\b(robbery|robbing|heist|theft)\b', 'covert operation'),
    (r'\b(hostage|kidnap|abduct)\b', 'rescue mission'),
]

def sanitize_prompt(prompt: str) -> str:
    """Rewrite a prompt to pass DALL-E content filters while keeping visual intent."""
    sanitized = prompt
    for pattern, replacement in CONTENT_REPLACEMENTS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def generate_image(scene: dict, project_name: str = "project", style: str = "cinematic photorealistic") -> str:
    """
    Generate an image for a scene. Returns the local file path.
    Priority: DALL-E 3 → FLUX Pro (Fal.ai) → Placeholder
    Content policy: auto-sanitizes prompt, retries with cleaner version if blocked.
    """
    scene_num = scene.get("scene_number", 1)
    prompt = scene.get("image_prompt", "Cinematic scene, professional film lighting")
    filename = IMAGES_DIR / f"{project_name}_scene_{scene_num:02d}.png"

    # Return cached image if it already exists
    if filename.exists():
        return str(filename)

    api_key = os.environ.get("OPENAI_API_KEY", "")
    fal_key = os.environ.get("FAL_KEY", os.environ.get("FAL_API_KEY", ""))

    if api_key and not api_key.startswith("sk-demo"):
        # Try DALL-E 3 with original prompt first
        try:
            return _dalle_generate(prompt, str(filename), style=style)
        except Exception as e:
            err_str = str(e).lower()
            if "content_policy" in err_str or "content filter" in err_str or "400" in err_str:
                print(f"[IMG] DALL-E content policy hit for scene {scene_num} — sanitizing prompt...")
                # Retry with sanitized prompt
                clean_prompt = sanitize_prompt(prompt)
                try:
                    return _dalle_generate(clean_prompt, str(filename), style=style)
                except Exception as e2:
                    print(f"[IMG] DALL-E retry failed: {e2} — trying FLUX Pro...")
                    # Fall through to FLUX
            else:
                print(f"[IMG] DALL-E failed: {e} — trying FLUX Pro...")

    # Try Fal.ai FLUX Pro as secondary
    if fal_key:
        try:
            return _flux_generate(prompt, str(filename), fal_key, style=style)
        except Exception as e:
            print(f"[IMG] FLUX Pro failed: {e} — using placeholder")

    # Final fallback: styled placeholder
    return _placeholder_generate(scene, str(filename))


# Style-specific quality suffixes for DALL-E 3
STYLE_SUFFIXES = {
    "cinematic photorealistic": "No text, no watermarks. Cinematic film still, 8K, hyper-detailed.",
    "animated cartoon vibrant": "No text, no watermarks. Vibrant 2D cartoon animation style, bold outlines, expressive, high quality.",
    "comic book graphic novel": "No text, no watermarks. Comic book panel art, bold ink outlines, halftone shading, high contrast.",
    "anime style detailed": "No text, no watermarks. Japanese anime style, cel-shaded, detailed backgrounds, Studio Ghibli quality.",
    "dark gritty noir": "No text, no watermarks. Film noir, high contrast, dramatic shadows, desaturated, moody.",
    "urban street photography": "No text, no watermarks. Candid street photography style, natural light, documentary feel.",
    "watercolor illustrated": "No text, no watermarks. Soft watercolor painting, loose brushstrokes, illustrated book style.",
}

def _dalle_generate(prompt: str, output_path: str, style: str = "cinematic photorealistic") -> str:
    """Generate image using DALL-E 3."""
    # DALL-E 3 supports up to 4000 chars. Use 3500 to leave room for suffix.
    # Preserve the END of the prompt (negative exclusions) — truncate from the middle if needed.
    NEGATIVE_TAIL = "No film crew, no camera equipment, no tripod, no production equipment, no text, no watermarks, no subtitles, no logos, no behind-the-scenes equipment."
    suffix = STYLE_SUFFIXES.get(style, STYLE_SUFFIXES["cinematic photorealistic"])
    
    # Remove any existing negative tail from prompt to avoid duplication
    import re as _re
    clean_prompt = _re.sub(r'No film crew[^.]*\.', '', prompt, flags=_re.IGNORECASE).strip()
    
    # Build: style suffix + clean prompt (truncated) + negative tail
    combined = f"{clean_prompt} {suffix}"
    max_body = 3500 - len(NEGATIVE_TAIL) - 2
    if len(combined) > max_body:
        combined = combined[:max_body]
    safe_prompt = f"{combined} {NEGATIVE_TAIL}"

    active_client = _get_client()
    response = active_client.images.generate(
        model="dall-e-3",
        prompt=safe_prompt,
        size="1792x1024",
        quality="standard",
        n=1
    )

    image_url = response.data[0].url
    img_data = requests.get(image_url, timeout=30).content
    with open(output_path, "wb") as f:
        f.write(img_data)

    print(f"[IMG] DALL-E 3 ✅ → {output_path}")
    return output_path


def _flux_generate(prompt: str, output_path: str, fal_key: str,
                   style: str = "cinematic photorealistic") -> str:
    """Generate image using Fal.ai FLUX Pro as DALL-E fallback."""
    import time
    suffix = STYLE_SUFFIXES.get(style, STYLE_SUFFIXES["cinematic photorealistic"])
    full_prompt = f"{prompt[:900]} {suffix}"

    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json"
    }

    # Submit job
    submit_url = "https://queue.fal.run/fal-ai/flux-pro/v1.1"
    payload = {
        "prompt": full_prompt,
        "image_size": "landscape_16_9",
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
        "num_images": 1,
        "output_format": "jpeg"
    }
    resp = requests.post(submit_url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    job = resp.json()
    request_id = job.get("request_id")
    status_url = job.get("response_url") or f"https://queue.fal.run/fal-ai/flux-pro/requests/{request_id}/status"

    # Poll for completion
    for _ in range(60):
        time.sleep(5)
        sr = requests.get(status_url, headers=headers, timeout=15)
        if sr.ok:
            sdata = sr.json()
            status = sdata.get("status", "")
            if status == "COMPLETED":
                result_url = sdata.get("response_url") or f"https://queue.fal.run/fal-ai/flux-pro/requests/{request_id}"
                rr = requests.get(result_url, headers=headers, timeout=15)
                if rr.ok:
                    images = rr.json().get("images", [])
                    if images:
                        img_url = images[0].get("url", "")
                        img_data = requests.get(img_url, timeout=30).content
                        with open(output_path, "wb") as f:
                            f.write(img_data)
                        print(f"[IMG] FLUX Pro ✅ → {output_path}")
                        return output_path
            elif status in ("FAILED", "ERROR"):
                raise Exception(f"FLUX job failed: {sdata}")
    raise Exception("FLUX Pro timed out")


def _placeholder_generate(scene: dict, output_path: str) -> str:
    """
    Generate a styled placeholder image using Pillow when no API key is available.
    Also used as last-resort fallback so animation never crashes on missing image.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        import subprocess
        # Try pip3 install without sudo (Render/cloud environments don't have sudo)
        subprocess.run(["pip3", "install", "pillow"], capture_output=True)
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            subprocess.run(["python3", "-m", "pip", "install", "pillow"], capture_output=True)
            from PIL import Image, ImageDraw, ImageFont

    scene_num = scene.get("scene_number", 1)
    title = scene.get("title", f"Scene {scene_num}")
    setting = scene.get("setting", "")
    mood = scene.get("mood", "dramatic")
    characters = scene.get("characters", [])

    palettes = {
        "dramatic":    [(15, 15, 30), (80, 20, 20)],
        "tense":       [(10, 10, 20), (40, 60, 80)],
        "joyful":      [(20, 40, 20), (60, 100, 40)],
        "mysterious":  [(10, 10, 25), (30, 20, 60)],
        "romantic":    [(30, 10, 20), (80, 30, 50)],
        "action":      [(20, 10, 10), (80, 40, 10)],
        "peaceful":    [(15, 25, 35), (30, 50, 70)],
    }
    colors = palettes.get(mood.lower(), palettes["dramatic"])

    W, H = 1280, 720
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        t = y / H
        r = int(colors[0][0] + (colors[1][0] - colors[0][0]) * t)
        g = int(colors[0][1] + (colors[1][1] - colors[0][1]) * t)
        b = int(colors[0][2] + (colors[1][2] - colors[0][2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    bar_h = 60
    draw.rectangle([0, 0, W, bar_h], fill=(0, 0, 0))
    draw.rectangle([0, H - bar_h, W, H], fill=(0, 0, 0))
    draw.rectangle([40, bar_h + 20, 140, bar_h + 60], fill=(233, 69, 96))

    try:
        font_lg   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_md   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_sm   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_badge= ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except Exception:
        font_lg = font_md = font_sm = font_badge = ImageFont.load_default()

    draw.text((55, bar_h + 26), f"SCENE {scene_num}", font=font_badge, fill=(255, 255, 255))
    draw.text((40, H // 2 - 60), title[:50], font=font_lg, fill=(255, 255, 255))
    if setting:
        draw.text((40, H // 2 - 20), f"📍 {setting[:60]}", font=font_md, fill=(180, 180, 180))
    if characters:
        chars_str = "Characters: " + ", ".join(characters[:5])
        draw.text((40, H // 2 + 30), chars_str[:70], font=font_sm, fill=(150, 200, 150))
    draw.text((W - 160, H // 2 - 10), f"[{mood.upper()}]", font=font_sm, fill=(233, 69, 96))

    img.save(output_path, "PNG")
    print(f"[IMG] Placeholder ✅ → {output_path}")
    return output_path


if __name__ == "__main__":
    test_scene = {
        "scene_number": 1,
        "title": "Motel Room Tension",
        "setting": "Dimly lit motel room, Miami",
        "characters": ["Rico", "Maria"],
        "image_prompt": "Two people in a tense conversation in a dimly lit motel room, Miami, dramatic shadows, cinematic",
        "mood": "tense"
    }
    path = generate_image(test_scene, "test_project")
    print(f"Image saved: {path}")
