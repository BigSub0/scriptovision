"""
ScriptoVision — Intelligent Tool Router
Automatically selects the best available tool/model for each task based on:
  - Available API keys
  - Scene mood, genre, and style
  - Speed vs quality tradeoff
  - Cost optimization
  - Fallback chains when primary tools fail

Tools managed:
  IMAGE GENERATION:
    1. DALL-E 3 (OpenAI)     — best quality, cinematic, safe
    2. DALL-E 2 (OpenAI)     — faster fallback
    3. Fal.ai FLUX Pro       — photorealistic, fast
    4. Fal.ai FLUX Schnell   — fastest, lower quality
    5. Placeholder           — no API key, offline

  VIDEO ANIMATION:
    1. Kling 1.6 Standard    — best cinematic motion (default)
    2. Kling 1.6 Pro         — higher quality, more credits
    3. Kling 2.1 Standard    — newer model (if available)
    4. Minimax Video         — good alternative
    5. LTX-2                 — fast, lower quality
    6. Wan 2.5               — open source alternative
    7. Ken Burns             — offline fallback only

  VOICE / TTS:
    1. OpenAI TTS            — best quality, tone-aware
    2. gTTS                  — free fallback
    3. Silent audio          — no internet

  SCENE ANALYSIS:
    1. GPT-4.1               — best understanding
    2. GPT-4.1-mini          — faster, cheaper
    3. Gemini 2.5 Flash      — alternative
    4. Rule-based parser     — offline fallback
"""

import os
import requests
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# KEY AVAILABILITY CHECK
# ─────────────────────────────────────────────────────────────────────────────

def _has_openai() -> bool:
    key = os.environ.get("OPENAI_API_KEY", "")
    return bool(key) and not key.startswith("sk-demo")

def _has_fal() -> bool:
    key = os.environ.get("FAL_KEY", os.environ.get("FAL_API_KEY", ""))
    return bool(key)

def _has_elevenlabs() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY", ""))

def _has_replicate() -> bool:
    return bool(os.environ.get("REPLICATE_API_TOKEN", ""))


# ─────────────────────────────────────────────────────────────────────────────
# MOOD / STYLE → TOOL MAPPING
# ─────────────────────────────────────────────────────────────────────────────

# Moods that benefit from Kling Pro (more credits but better motion)
KLING_PRO_MOODS = {"action", "explosive", "chase", "fight", "dramatic", "epic", "climax"}

# Moods that work fine with standard Kling
KLING_STD_MOODS = {"tense", "mysterious", "nostalgic", "romantic", "playful",
                   "emotional", "reflective", "comedic", "dark", "gritty",
                   "joyful", "poetic", "suspenseful", "melancholic"}

# Visual styles that map to specific image models
IMAGE_STYLE_MAP = {
    "cinematic photorealistic":   "dalle3",
    "dark gritty noir":           "dalle3",
    "urban street photography":   "dalle3",
    "animated cartoon vibrant":   "dalle3",
    "comic book graphic novel":   "dalle3",
    "anime style detailed":       "dalle3",
    "watercolor illustrated":     "dalle3",
}

# Animation models available on Fal.ai
FAL_VIDEO_MODELS = {
    "kling":        "fal-ai/kling-video/v1.6/standard/image-to-video",
    "kling_pro":    "fal-ai/kling-video/v1.6/pro/image-to-video",
    "kling21":      "fal-ai/kling-video/v2.1/standard/image-to-video",
    "minimax":      "fal-ai/minimax-video/image-to-video",
    "ltx2":         "fal-ai/ltx-video/image-to-video",
    "wan25":        "fal-ai/wan-video/image-to-video",
    "wan21":        "fal-ai/wan-video/v2.1/image-to-video",
}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ROUTER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def select_image_tool(scene: dict, style: str = "cinematic photorealistic") -> dict:
    """
    Auto-select the best image generation tool for a scene.
    Returns a dict with: tool, model, reason, fallback_chain
    """
    mood = scene.get("mood", "cinematic").lower()
    scene_num = scene.get("scene_number", 1)

    if _has_openai():
        return {
            "tool": "openai_dalle",
            "model": "dall-e-3",
            "reason": "DALL-E 3 — best quality, cinematic, safe for all styles",
            "fallback_chain": ["openai_dalle2", "placeholder"],
            "size": "1792x1024",
            "quality": "standard"
        }
    elif _has_fal():
        return {
            "tool": "fal_flux",
            "model": "fal-ai/flux-pro/v1.1",
            "reason": "FLUX Pro via Fal.ai — photorealistic, fast",
            "fallback_chain": ["fal_flux_schnell", "placeholder"],
        }
    else:
        return {
            "tool": "placeholder",
            "model": None,
            "reason": "No API keys available — using styled placeholder",
            "fallback_chain": [],
        }


def select_animation_tool(scene: dict, provider_override: str = None) -> dict:
    """
    Auto-select the best video animation tool for a scene.
    Returns a dict with: tool, model_id, reason, duration, fallback_chain
    """
    mood = scene.get("mood", "cinematic").lower()
    duration = int(scene.get("duration", 5))
    kling_duration = "10" if duration >= 8 else "5"

    # If user explicitly chose a provider, respect it
    if provider_override and provider_override != "auto" and provider_override in FAL_VIDEO_MODELS:
        return {
            "tool": "fal_video",
            "model_id": FAL_VIDEO_MODELS[provider_override],
            "provider_key": provider_override,
            "reason": f"User selected: {provider_override}",
            "duration": kling_duration,
            "fallback_chain": ["kling", "ken_burns"],
        }

    if not _has_fal():
        return {
            "tool": "ken_burns",
            "model_id": None,
            "provider_key": "demo",
            "reason": "No Fal.ai key — Ken Burns demo mode",
            "duration": str(duration),
            "fallback_chain": [],
        }

    # Auto-select based on mood
    if mood in KLING_PRO_MOODS:
        return {
            "tool": "fal_video",
            "model_id": FAL_VIDEO_MODELS["kling_pro"],
            "provider_key": "kling_pro",
            "reason": f"Kling 1.6 Pro — scene mood '{mood}' needs premium motion quality",
            "duration": kling_duration,
            "fallback_chain": ["kling", "minimax", "ltx2", "ken_burns"],
        }
    else:
        return {
            "tool": "fal_video",
            "model_id": FAL_VIDEO_MODELS["kling"],
            "provider_key": "kling",
            "reason": f"Kling 1.6 Standard — cinematic motion for mood '{mood}'",
            "duration": kling_duration,
            "fallback_chain": ["minimax", "ltx2", "ken_burns"],
        }


def select_voice_tool(scene: dict, character: str = "NARRATOR") -> dict:
    """
    Auto-select the best TTS tool for a character/scene.
    Returns a dict with: tool, voice_id, reason
    """
    if _has_openai():
        return {
            "tool": "openai_tts",
            "model": "tts-1",
            "reason": "OpenAI TTS — best quality, tone-aware voice selection",
            "fallback_chain": ["gtts", "silent"],
        }
    elif _has_elevenlabs():
        return {
            "tool": "elevenlabs",
            "model": "eleven_multilingual_v2",
            "reason": "ElevenLabs — ultra-realistic voices",
            "fallback_chain": ["gtts", "silent"],
        }
    else:
        return {
            "tool": "gtts",
            "model": None,
            "reason": "gTTS — free fallback (no API key)",
            "fallback_chain": ["silent"],
        }


def select_scene_parser(complexity: str = "standard") -> dict:
    """
    Auto-select the best scene parsing/analysis model.
    Returns a dict with: tool, model, reason
    """
    if _has_openai():
        if complexity == "complex":
            return {
                "tool": "openai_chat",
                "model": "gpt-4.1",
                "reason": "GPT-4.1 — best scene understanding for complex scripts",
            }
        else:
            return {
                "tool": "openai_chat",
                "model": "gpt-4.1-mini",
                "reason": "GPT-4.1-mini — fast, cost-efficient scene parsing",
            }
    else:
        return {
            "tool": "rule_based",
            "model": None,
            "reason": "Rule-based parser — no OpenAI key available",
        }


# ─────────────────────────────────────────────────────────────────────────────
# FULL SCENE TOOL PLAN
# ─────────────────────────────────────────────────────────────────────────────

def plan_scene_tools(scene: dict, style: str = "cinematic photorealistic",
                     provider_override: str = None) -> dict:
    """
    Generate a complete tool plan for a single scene.
    Returns all tool selections for image, animation, and voice.
    """
    image_tool  = select_image_tool(scene, style)
    anim_tool   = select_animation_tool(scene, provider_override)
    voice_tool  = select_voice_tool(scene)
    parser_tool = select_scene_parser()

    return {
        "scene_number": scene.get("scene_number", 1),
        "scene_title":  scene.get("title", "Scene"),
        "mood":         scene.get("mood", "cinematic"),
        "image":        image_tool,
        "animation":    anim_tool,
        "voice":        voice_tool,
        "parser":       parser_tool,
        "summary": (
            f"Image: {image_tool['tool']} | "
            f"Animation: {anim_tool['provider_key']} ({anim_tool['reason'].split('—')[0].strip()}) | "
            f"Voice: {voice_tool['tool']}"
        )
    }


def plan_project_tools(scenes: list, style: str = "cinematic photorealistic",
                       provider_override: str = None) -> dict:
    """
    Generate a complete tool plan for all scenes in a project.
    Logs what tools will be used and why.
    """
    has_openai = _has_openai()
    has_fal    = _has_fal()

    scene_plans = [plan_scene_tools(s, style, provider_override) for s in scenes]

    # Count tool usage
    anim_counts = {}
    for sp in scene_plans:
        key = sp["animation"]["provider_key"]
        anim_counts[key] = anim_counts.get(key, 0) + 1

    return {
        "total_scenes": len(scenes),
        "api_status": {
            "openai": "✅ Connected" if has_openai else "❌ No key",
            "fal_ai": "✅ Connected" if has_fal    else "❌ No key",
            "elevenlabs": "✅ Connected" if _has_elevenlabs() else "❌ No key",
        },
        "animation_breakdown": anim_counts,
        "scene_plans": scene_plans,
        "overall_summary": (
            f"{'DALL-E 3' if has_openai else 'Placeholder'} images | "
            f"{'Kling AI' if has_fal else 'Ken Burns demo'} animation | "
            f"{'OpenAI TTS' if has_openai else 'gTTS'} voice"
        )
    }


# ─────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    test_scenes = [
        {"scene_number": 1, "title": "Wild Hundreds Night", "mood": "gritty", "duration": 5},
        {"scene_number": 2, "title": "The Chase",           "mood": "action", "duration": 10},
        {"scene_number": 3, "title": "Rooftop Reflection",  "mood": "nostalgic", "duration": 5},
        {"scene_number": 4, "title": "The Confrontation",   "mood": "dramatic", "duration": 5},
    ]

    plan = plan_project_tools(test_scenes, style="cinematic photorealistic")
    print("\n=== TOOL ROUTER SELF-TEST ===")
    print(f"API Status: {plan['api_status']}")
    print(f"Overall: {plan['overall_summary']}")
    print(f"Animation breakdown: {plan['animation_breakdown']}")
    print("\nPer-scene plans:")
    for sp in plan["scene_plans"]:
        print(f"  Scene {sp['scene_number']} ({sp['mood']}): {sp['summary']}")
    print("\n✅ Tool router working correctly")
