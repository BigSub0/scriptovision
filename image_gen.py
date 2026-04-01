"""
ScriptoVision — Image Generation Module
Generates a scene image from a prompt using DALL-E 3.
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

client = _get_client()

IMAGES_DIR = Path(os.environ.get("BASE_DIR", "/home/ubuntu/scriptovision")) / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def generate_image(scene: dict, project_name: str = "project", style: str = "cinematic photorealistic") -> str:
    """
    Generate an image for a scene. Returns the local file path.
    Uses DALL-E 3 if API key is available, otherwise creates a placeholder.
    """
    scene_num = scene.get("scene_number", 1)
    prompt = scene.get("image_prompt", "Cinematic scene, professional film lighting")
    filename = IMAGES_DIR / f"{project_name}_scene_{scene_num:02d}.png"

    # Return cached image if it already exists
    if filename.exists():
        return str(filename)

    api_key = os.environ.get("OPENAI_API_KEY", "")

    if api_key and not api_key.startswith("sk-demo"):
        return _dalle_generate(prompt, str(filename), style=style)
    else:
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
    # Ensure prompt is safe and within limits
    safe_prompt = prompt[:900]
    suffix = STYLE_SUFFIXES.get(style, STYLE_SUFFIXES["cinematic photorealistic"])
    safe_prompt += f" {suffix}"

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

    return output_path


def _placeholder_generate(scene: dict, output_path: str) -> str:
    """
    Generate a styled placeholder image using Pillow when no API key is available.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        import subprocess
        subprocess.run(["sudo", "pip3", "install", "pillow"], capture_output=True)
        from PIL import Image, ImageDraw, ImageFont

    scene_num = scene.get("scene_number", 1)
    title = scene.get("title", f"Scene {scene_num}")
    setting = scene.get("setting", "")
    mood = scene.get("mood", "dramatic")
    characters = scene.get("characters", [])

    # Color palette based on mood
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

    # Gradient background
    for y in range(H):
        t = y / H
        r = int(colors[0][0] + (colors[1][0] - colors[0][0]) * t)
        g = int(colors[0][1] + (colors[1][1] - colors[0][1]) * t)
        b = int(colors[0][2] + (colors[1][2] - colors[0][2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Cinematic bars
    bar_h = 60
    draw.rectangle([0, 0, W, bar_h], fill=(0, 0, 0))
    draw.rectangle([0, H - bar_h, W, H], fill=(0, 0, 0))

    # Scene number badge
    draw.rectangle([40, bar_h + 20, 140, bar_h + 60], fill=(233, 69, 96))
    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_badge = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except Exception:
        font_lg = font_md = font_sm = font_badge = ImageFont.load_default()

    draw.text((55, bar_h + 26), f"SCENE {scene_num}", font=font_badge, fill=(255, 255, 255))

    # Title
    draw.text((40, H // 2 - 60), title[:50], font=font_lg, fill=(255, 255, 255))

    # Setting
    if setting:
        draw.text((40, H // 2 - 20), f"📍 {setting[:60]}", font=font_md, fill=(180, 180, 180))

    # Characters
    if characters:
        chars_str = "Characters: " + ", ".join(characters[:5])
        draw.text((40, H // 2 + 30), chars_str[:70], font=font_sm, fill=(150, 200, 150))

    # Mood tag
    draw.text((W - 160, H // 2 - 10), f"[{mood.upper()}]", font=font_sm, fill=(233, 69, 96))

    # Demo watermark
    draw.text((W - 220, H - bar_h - 30), "DEMO — Add API Key for Real Images",
              font=font_sm, fill=(100, 100, 100))

    img.save(output_path, "PNG")
    return output_path


if __name__ == "__main__":
    test_scene = {
        "scene_number": 1,
        "title": "The Wild Hundreds",
        "setting": "South side Chicago street at night",
        "characters": ["Sub", "Friend"],
        "image_prompt": "Cinematic night scene on a Chicago south side street, neon lights reflecting on wet pavement, two young men walking, dramatic shadows, film noir atmosphere",
        "mood": "dramatic"
    }
    path = generate_image(test_scene, "test_project")
    print(f"Image saved: {path}")
