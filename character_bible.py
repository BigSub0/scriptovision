"""
ScriptoVision — Character Bible System
=======================================
Permanent registry for recurring characters.
Each character has:
  - A locked FACE SEED: exact physical description used in EVERY image prompt
  - A locked VOICE ID: ElevenLabs voice ID used in EVERY TTS call
  - Clothing is NOT locked — it changes per scene (that's intentional)

The bible is stored as a JSON file on disk so it persists across restarts.
Characters defined here override anything GPT tries to invent.
"""

import os
import json
from pathlib import Path

# Bible file lives in the same persistent storage as jobs
_BASE = Path(os.environ.get("BASE_DIR", "/home/ubuntu/scriptovision"))

# Try persistent disk first, fall back to project dir
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
    "liam":      "TX3LPaxmHKxFdv7VOQHJ",   # Deep, authoritative
    "brian":     "nPczCjzI2devNBz1zQrb",   # Clear, conversational male
    "daniel":    "onwK4e9ZLuTAKqWW03F9",   # Expressive, British
    "adam":      "pNInz6obpgDQGcFmaJgB",   # Deep, American male
    "charlie":   "IKne3meq5aSn9XLyUdCD",   # Natural, casual male
    "george":    "JBFqnCBsd6RMkjVDRZzb",   # Warm, British male
    "callum":    "N2lVS1w4EtoT3dr4eOWO",   # Intense, American male
    "clyde":     "2EiwWnXFnvU5JabPnv8n",   # Middle-aged, American male
    "dave":      "CYw3kZ02Hs0563khs1Fj",   # British-Essex, casual
    "fin":       "D38z5RcWu1voky8WS1ja",   # Irish, calm male
    "glinda":    "z9fAnlkpzviPz146aGWa",   # Witch-like, dramatic female
    # Female voices
    "sarah":     "EXAVITQu4vr4xnSDxMaL",   # Warm, natural female
    "charlotte": "XB0fDUnXU5powFXDhCwa",   # Light, youthful female
    "lily":      "pFZP5JQG7iQjIQuC4Bku",   # Neutral, versatile
    "rachel":    "21m00Tcm4TlvDq8ikWAM",   # Calm, American female
    "domi":      "AZnzlk1XvdvUeBnXmlld",   # Strong, American female
    "bella":     "EXAVITQu4vr4xnSDxMaL",   # Warm female
    "elli":      "MF3mGyEYCl7XYWbV9V6O",   # Young, American female
    "grace":     "oWAxZDx7w5VEj9dCyTzz",   # Southern American female
    "jessica":   "cgSgspJ2msm6clMCkdW9",   # Expressive, American female
    "matilda":   "XrExE9yKIg1WjnnlVkGX",   # Warm, American female
}

# Default voice assignments by gender/type (fallback if not in bible)
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
    """Load the character bible from disk. Returns empty dict if not found."""
    if BIBLE_PATH.exists():
        try:
            return json.loads(BIBLE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_bible(bible: dict):
    """Save the character bible to disk."""
    BIBLE_PATH.write_text(json.dumps(bible, indent=2), encoding="utf-8")


def add_character(name: str, face_seed: str, voice_name: str,
                  gender: str = "male", description: str = "") -> dict:
    """
    Add or update a character in the bible.
    
    Args:
        name: Character name (e.g. "AMANI", "MARCUS")
        face_seed: Exact physical description for image prompts.
                   Example: "Black woman, early 30s, natural afro hair, 
                   high cheekbones, full lips, warm brown skin, athletic build"
        voice_name: ElevenLabs voice name from ELEVENLABS_VOICES dict
                    (e.g. "sarah", "liam", "brian")
        gender: "male" or "female"
        description: Optional character bio/notes
    """
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
    """Get a character from the bible by name. Returns None if not found."""
    bible = load_bible()
    return bible.get(name.upper().strip())


def get_all_characters() -> dict:
    """Return the full character bible."""
    return load_bible()


def delete_character(name: str):
    """Remove a character from the bible."""
    bible = load_bible()
    bible.pop(name.upper().strip(), None)
    save_bible(bible)


# ─────────────────────────────────────────────────────────────────────────────
# FACE SEED INJECTION — used by scene_parser.py
# ─────────────────────────────────────────────────────────────────────────────

def build_character_references_from_bible() -> dict:
    """
    Build the character_references dict that scene_parser.py expects.
    Returns: {CHARACTER_NAME: face_seed_string}
    """
    bible = load_bible()
    refs = {}
    for name, char in bible.items():
        face_seed = char.get("face_seed", "")
        if face_seed:
            refs[name] = face_seed
    return refs


def inject_face_seeds_into_prompt(image_prompt: str, characters_in_scene: list) -> str:
    """
    Takes an image_prompt and a list of character names.
    Ensures each character's face_seed is present in the prompt.
    If GPT forgot to include it, appends it.
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
        # Check if the face seed is already in the prompt (partial match)
        # Use first 40 chars of face seed as fingerprint
        fingerprint = face_seed[:40].lower()
        if fingerprint not in prompt.lower():
            # Append the face seed
            prompt += f" Character {char_key}: {face_seed}."
    
    return prompt


# ─────────────────────────────────────────────────────────────────────────────
# VOICE ID LOOKUP — used by tts_engine.py
# ─────────────────────────────────────────────────────────────────────────────

def get_voice_id_for_character(character_name: str) -> str | None:
    """
    Get the locked ElevenLabs voice ID for a character.
    Returns None if character not in bible (fall back to tone-based selection).
    """
    char = get_character(character_name)
    if char:
        return char.get("voice_id")
    return None


def get_voice_name_for_character(character_name: str) -> str | None:
    """Get the voice name (e.g. 'sarah', 'liam') for a character."""
    char = get_character(character_name)
    if char:
        return char.get("voice_name")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# STYLE LOCK — ensures art style stays consistent
# ─────────────────────────────────────────────────────────────────────────────

STYLE_LOCK_FILE = _BASE / "style_lock.json"

def save_style_lock(style: str, visual_style_prompt: str = None):
    """Save the locked visual style for this project."""
    data = {
        "style": style,
        "visual_style_prompt": visual_style_prompt or style
    }
    STYLE_LOCK_FILE.write_text(json.dumps(data), encoding="utf-8")


def load_style_lock() -> dict:
    """Load the locked visual style."""
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
    # Test: add a character and retrieve them
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
