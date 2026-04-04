"""
ScriptoVision — Character Bible System
=======================================
Permanent registry for recurring characters.
Each character has:
  - A locked FACE SEED: exact physical description used in EVERY image prompt
  - A locked VOICE ID: ElevenLabs voice ID used in EVERY TTS call
  - Clothing is NOT locked — it changes per scene (that's intentional)

The bible is stored as a JSON file on disk so it persists across restarts.
Characters defined here OVERRIDE anything GPT tries to invent.
"""

import os
import json
import re
from pathlib import Path

_BASE = Path(os.environ.get("BASE_DIR", "/home/ubuntu/scriptovision"))

def _get_bible_path() -> Path:
    var_data = Path("/var/data")
    if var_data.exists():
        try:
            p = var_data / "character_bible.json"
            p.touch()
            return p
        except Exception:
            pass
    return _BASE / "character_bible.json"

BIBLE_PATH = _get_bible_path()

# ─────────────────────────────────────────────────────────────────────────────
# ElevenLabs voice IDs — pre-made voices, no custom training needed
# ─────────────────────────────────────────────────────────────────────────────
ELEVENLABS_VOICES = {
    # Male voices
    "liam":      "TX3LPaxmHKxFdv7VOQHJ",
    "brian":     "nPczCjzI2devNBz1zQrb",
    "daniel":    "onwK4e9ZLuTAKqWW03F9",
    "adam":      "pNInz6obpgDQGcFmaJgB",
    "charlie":   "IKne3meq5aSn9XLyUdCD",
    "george":    "JBFqnCBsd6RMkjVDRZzb",
    "callum":    "N2lVS1w4EtoT3dr4eOWO",
    "clyde":     "2EiwWnXFnvU5JabPnv8n",
    "dave":      "CYw3kZ02Hs0563khs1Fj",
    "fin":       "D38z5RcWu1voky8WS1ja",
    "glinda":    "z9fAnlkpzviPz146aGWa",
    # Female voices
    "sarah":     "EXAVITQu4vr4xnSDxMaL",
    "charlotte": "XB0fDUnXU5powFXDhCwa",
    "lily":      "pFZP5JQG7iQjIQuC4Bku",
    "rachel":    "21m00Tcm4TlvDq8ikWAM",
    "domi":      "AZnzlk1XvdvUeBnXmlld",
    "bella":     "EXAVITQu4vr4xnSDxMaL",
    "elli":      "MF3mGyEYCl7XYWbV9V6O",
    "grace":     "oWAxZDx7w5VEj9dCyTzz",
    "jessica":   "cgSgspJ2msm6clMCkdW9",
    "matilda":   "XrExE9yKIg1WjnnlVkGX",
}

DEFAULT_VOICE_BY_TYPE = {
    "male_deep":     "liam",
    "male_mid":      "brian",
    "male_young":    "charlie",
    "female_warm":   "sarah",
    "female_young":  "charlotte",
    "narrator":      "liam",
}


# ─────────────────────────────────────────────────────────────────────────────
# BIBLE CRUD
# ─────────────────────────────────────────────────────────────────────────────

def load_bible() -> dict:
    if BIBLE_PATH.exists():
        try:
            return json.loads(BIBLE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_bible(bible: dict):
    BIBLE_PATH.write_text(json.dumps(bible, indent=2), encoding="utf-8")


def add_character(name: str, face_seed: str, voice_name: str,
                  gender: str = "male", description: str = "") -> dict:
    bible = load_bible()
    char_key = name.upper().strip()
    voice_id = ELEVENLABS_VOICES.get(voice_name.lower(), ELEVENLABS_VOICES["liam"])
    bible[char_key] = {
        "name": char_key,
        "face_seed": face_seed.strip(),
        "voice_name": voice_name.lower(),
        "voice_id": voice_id,
        "gender": gender,
        "description": description,
    }
    save_bible(bible)
    return bible[char_key]


def get_character(name: str) -> dict | None:
    bible = load_bible()
    return bible.get(name.upper().strip())


def get_all_characters() -> dict:
    return load_bible()


def delete_character(name: str):
    bible = load_bible()
    bible.pop(name.upper().strip(), None)
    save_bible(bible)


# ─────────────────────────────────────────────────────────────────────────────
# FACE SEED INJECTION — HARD REPLACE, not append-only
# ─────────────────────────────────────────────────────────────────────────────

def build_character_references_from_bible() -> dict:
    """Build the character_references dict that scene_parser.py expects."""
    bible = load_bible()
    refs = {}
    for name, char in bible.items():
        face_seed = char.get("face_seed", "")
        if face_seed:
            refs[name] = face_seed
    return refs


def inject_face_seeds_into_prompt(image_prompt: str, characters_in_scene: list) -> str:
    """
    HARD ENFORCEMENT: For each character in the scene, find any existing description
    GPT wrote for them and REPLACE it with the bible's locked face seed.
    If no existing description found, appends it.
    
    This prevents DALL-E from getting two conflicting character descriptions.
    """
    bible = load_bible()
    prompt = image_prompt

    for char_name in characters_in_scene:
        char_key = char_name.upper().strip()
        char = bible.get(char_key)
        if not char:
            continue
        face_seed = char.get("face_seed", "")
        if not face_seed:
            continue

        # Build the canonical character block
        canonical = f"[{char_key}: {face_seed}]"

        # Remove any existing description GPT wrote for this character
        # Pattern: CHARACTER_NAME followed by a description up to the next character block or end
        # Try to find and remove patterns like "Character NAME: ...", "NAME: ...", "[NAME: ...]"
        patterns = [
            rf'\[{re.escape(char_key)}:[^\]]*\]',                    # [NAME: ...]
            rf'Character {re.escape(char_key)}:[^.\[]*\.',            # Character NAME: ...
            rf'\b{re.escape(char_key)}:[^.\[]*\.',                    # NAME: ...
        ]
        for pat in patterns:
            prompt = re.sub(pat, '', prompt, flags=re.IGNORECASE)

        # Now inject the canonical description
        # Place it right after the style prefix (first sentence) for maximum weight
        if canonical not in prompt:
            # Find end of first sentence (after style description)
            first_period = prompt.find('.')
            if first_period > 0 and first_period < 200:
                prompt = prompt[:first_period + 1] + f" {canonical}" + prompt[first_period + 1:]
            else:
                prompt = f"{canonical} " + prompt

    return prompt


def enforce_negative_prompt(image_prompt: str) -> str:
    """
    Ensure the negative exclusion clause is always at the end of the prompt,
    regardless of truncation. Removes any existing version first, then appends.
    """
    NEGATIVE = "No film crew, no camera equipment, no tripod, no production equipment, no text, no watermarks, no subtitles, no logos, no behind-the-scenes equipment."
    # Remove any existing negative prompt to avoid duplication
    prompt = re.sub(
        r'No film crew[^.]*\.',
        '',
        image_prompt,
        flags=re.IGNORECASE
    ).strip()
    return f"{prompt} {NEGATIVE}"


# ─────────────────────────────────────────────────────────────────────────────
# VOICE ID LOOKUP — used by tts_engine.py
# ─────────────────────────────────────────────────────────────────────────────

def get_voice_id_for_character(character_name: str) -> str | None:
    char = get_character(character_name)
    if char:
        return char.get("voice_id")
    return None


def get_voice_name_for_character(character_name: str) -> str | None:
    char = get_character(character_name)
    if char:
        return char.get("voice_name")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# STYLE LOCK
# ─────────────────────────────────────────────────────────────────────────────

STYLE_LOCK_FILE = _BASE / "style_lock.json"

def save_style_lock(style: str, visual_style_prompt: str = None):
    data = {
        "style": style,
        "visual_style_prompt": visual_style_prompt or style
    }
    STYLE_LOCK_FILE.write_text(json.dumps(data), encoding="utf-8")


def load_style_lock() -> dict:
    if STYLE_LOCK_FILE.exists():
        try:
            return json.loads(STYLE_LOCK_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# CLI — quick test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    add_character(
        name="AMANI",
        face_seed="Black woman, early 30s, natural afro hair, high cheekbones, full lips, warm brown skin, athletic build, determined expression",
        voice_name="sarah",
        gender="female",
        description="Main female protagonist"
    )
    add_character(
        name="MARCUS",
        face_seed="Black man, late 20s, low fade haircut, sharp jawline, dark brown skin, muscular build, intense eyes, slight beard",
        voice_name="callum",
        gender="male",
        description="Male lead"
    )
    print("Bible:", json.dumps(get_all_characters(), indent=2))
    print("Voice ID for AMANI:", get_voice_id_for_character("AMANI"))
    print("Refs:", build_character_references_from_bible())
