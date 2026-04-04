"""
ScriptoVision — TTS / Voiceover Engine v3
=========================================
VOICE PRIORITY (absolute, no exceptions):
  1. Character Bible voice_id  → used directly with ElevenLabs API (LOCKED, cannot be overridden)
  2. User voice_map override   → only applies when character is NOT in bible
  3. Named character role map  → only applies when character is NOT in bible
  4. Dialogue tone inference   → only applies when character is NOT in bible
  5. Scene mood fallback       → only applies when character is NOT in bible
  6. Default: onyx (deep male) → last resort

If a character is in the Character Bible, their voice_id is used DIRECTLY.
No tone matching, no mood fallback, no override can change a bible-locked voice.
"""
import os
import re
import json
import subprocess
from pathlib import Path
from openai import OpenAI

def _get_client():
    api_key = os.environ.get("OPENAI_API_KEY", "")
    return OpenAI(api_key=api_key, base_url="https://api.openai.com/v1")

client = _get_client()

AUDIO_DIR = Path(os.environ.get("BASE_DIR", "/home/ubuntu/scriptovision")) / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ─── ElevenLabs pre-made voice IDs ────────────────────────────────────────────
ELEVENLABS_VOICE_MAP = {
    # Deep authoritative males
    "onyx":    "TX3LPaxmHKxFdv7VOQHJ",  # Liam — deep, authoritative
    "liam":    "TX3LPaxmHKxFdv7VOQHJ",
    # Clear conversational males
    "echo":    "nPczCjzI2devNBz1zQrb",  # Brian — clear, conversational
    "brian":   "nPczCjzI2devNBz1zQrb",
    # Expressive storyteller (British)
    "fable":   "onwK4e9ZLuTAKqWW03F9",  # Daniel — expressive, theatrical
    "daniel":  "onwK4e9ZLuTAKqWW03F9",
    # Warm natural female
    "nova":    "EXAVITQu4vr4xnSDxMaL",  # Sarah — warm, natural
    "sarah":   "EXAVITQu4vr4xnSDxMaL",
    # Light youthful female
    "shimmer": "XB0fDUnXU5powFXDhCwa",  # Charlotte — light, youthful
    "charlotte":"XB0fDUnXU5powFXDhCwa",
    # Neutral versatile
    "alloy":   "pFZP5JQG7iQjIQuC4Bku",  # Lily — neutral
    "lily":    "pFZP5JQG7iQjIQuC4Bku",
    # Additional male voices
    "george":  "JBFqnCBsd6RMkjVDRZzb",
    "callum":  "N2lVS1w4EtoT3dr4eOWO",
    "clyde":   "2EiwWnXFnvU5JabPnv8n",
    "dave":    "CYw3kZ02Hs0563khs1Fj",
    "charlie": "IKne3meq5aSn9XLyUdCD",
    "adam":    "pNInz6obpgDQGcFmaJgB",
    "fin":     "D38z5RcWu1voky8WS1ja",
    # Additional female voices
    "rachel":  "21m00Tcm4TlvDq8ikWAM",
    "domi":    "AZnzlk1XvdvUeBnXmlld",
    "bella":   "EXAVITQu4vr4xnSDxMaL",
    "elli":    "MF3mGyEYCl7XYWbV9V6O",
    "grace":   "oWAxZDx7w5VEj9dCyTzz",
    "jessica": "cgSgspJ2msm6clMCkdW9",
    "matilda": "XrExE9yKIg1WjnnlVkGX",
}

# ─── OpenAI voice descriptions for UI ─────────────────────────────────────────
VOICE_DESCRIPTIONS = {
    "onyx":    "Deep & Authoritative (Morgan Freeman-esque)",
    "echo":    "Clear Male, Conversational",
    "fable":   "Expressive Storyteller, Theatrical",
    "nova":    "Warm Female, Natural",
    "shimmer": "Light Female, Youthful",
    "alloy":   "Neutral, Versatile",
}

# ─── Narrator voice by scene mood ─────────────────────────────────────────────
MOOD_NARRATOR_VOICE = {
    "dramatic": "onyx", "tense": "onyx", "dark": "onyx", "noir": "onyx",
    "serious": "onyx", "gritty": "onyx", "intense": "onyx",
    "melancholy": "onyx", "somber": "onyx", "suspenseful": "onyx",
    "emotional": "fable", "nostalgic": "fable", "reflective": "fable",
    "hopeful": "fable", "inspiring": "fable", "bittersweet": "fable",
    "poetic": "fable", "mysterious": "fable",
    "action": "echo", "exciting": "echo", "energetic": "echo",
    "confident": "echo", "bold": "echo",
    "playful": "shimmer", "comedic": "shimmer", "funny": "shimmer",
    "lighthearted": "shimmer",
    "joyful": "nova", "romantic": "nova", "warm": "nova",
    "default": "onyx",
}

# ─── Named character role fallbacks (only used if NOT in bible) ───────────────
CHARACTER_VOICE_OVERRIDES = {
    "sub": "onyx", "sernard": "onyx", "narrator": "onyx",
    "vo": "onyx", "voiceover": "onyx",
    "villain": "fable", "antagonist": "fable",
    "boss": "onyx", "detective": "onyx", "officer": "onyx",
    "cop": "onyx", "soldier": "onyx", "elder": "onyx",
    "grandfather": "onyx", "father": "echo", "dad": "echo",
    "brother": "echo", "friend": "echo", "homie": "echo",
    "dj": "echo", "host": "echo", "announcer": "echo",
    "reporter": "alloy", "teacher": "alloy", "doctor": "alloy",
    "mother": "nova", "mom": "nova", "sister": "nova",
    "girl": "nova", "woman": "nova", "lady": "nova",
    "child": "shimmer", "kid": "shimmer", "boy": "shimmer",
}

# ─── Tone keywords ─────────────────────────────────────────────────────────────
TONE_KEYWORDS = {
    "aggressive": ["get out", "back off", "don't", "stop", "never", "shut up",
                   "move", "now!", "i said", "you better", "i'm warning"],
    "angry": ["how dare", "i can't believe", "unbelievable", "you always",
              "you never", "i'm done", "enough", "forget it"],
    "commanding": ["listen up", "everybody", "attention", "fall in", "stand down",
                   "move out", "let's go", "on my signal", "do it now", "execute"],
    "caring": ["i love you", "are you okay", "i'm here", "don't worry",
               "i've got you", "you matter", "i care", "be safe", "come home"],
    "gentle": ["it's okay", "take your time", "breathe", "relax", "easy now",
               "no rush", "you're safe", "i understand"],
    "sarcastic": ["oh sure", "right", "yeah right", "of course", "wow thanks",
                  "great idea", "brilliant", "oh really", "sure thing"],
    "excited": ["yes!", "let's go!", "finally!", "i can't believe it!", "amazing!",
                "this is it!", "we did it!", "no way!", "oh my god"],
    "playful": ["haha", "lol", "you're funny", "gotcha", "bet", "for real though",
                "come on", "stop playing", "you wild"],
}

DIALOGUE_TONE_VOICE = {
    "aggressive": "onyx", "angry": "onyx", "commanding": "onyx",
    "caring": "nova", "gentle": "nova",
    "sarcastic": "fable", "excited": "shimmer", "playful": "shimmer",
    "neutral": "echo", "default": "echo",
}


def infer_dialogue_tone(line_text: str) -> str:
    text_lower = line_text.lower()
    for tone, keywords in TONE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return tone
    if line_text.count("!") >= 2:
        return "excited"
    if line_text.endswith("?") and len(line_text) < 30:
        return "gentle"
    if line_text.isupper() and len(line_text) > 5:
        return "aggressive"
    return "neutral"


def get_voice_for_narrator(mood: str) -> str:
    mood_lower = (mood or "default").lower().strip()
    return MOOD_NARRATOR_VOICE.get(mood_lower, MOOD_NARRATOR_VOICE["default"])


def _lookup_bible_voice_id(character_name: str) -> str | None:
    """
    Direct bible lookup — returns ElevenLabs voice_id if character is in bible.
    Returns None if not found. This is the ONLY path for bible characters.
    """
    try:
        from character_bible import get_voice_id_for_character
        voice_id = get_voice_id_for_character(character_name)
        if voice_id:
            print(f"[TTS/Bible] {character_name} → locked voice_id: {voice_id[:20]}...")
            return voice_id
    except Exception as e:
        print(f"[TTS/Bible] Lookup error for {character_name}: {e}")
    return None


def get_voice_for_character(character_name: str, line_text: str = "",
                             scene_mood: str = "", voice_map: dict = None) -> str:
    """
    Returns an OpenAI-style voice name for fallback use (non-bible characters only).
    Bible characters should use _lookup_bible_voice_id() directly.
    """
    name_lower = (character_name or "").lower().strip()

    # 1. User-provided override
    if voice_map:
        vm_lower = {k.lower(): v for k, v in voice_map.items()}
        if name_lower in vm_lower:
            return vm_lower[name_lower]
        for key, voice in vm_lower.items():
            if key in name_lower or name_lower in key:
                return voice

    # 2. Named character role override
    if name_lower in CHARACTER_VOICE_OVERRIDES:
        return CHARACTER_VOICE_OVERRIDES[name_lower]
    for key, voice in CHARACTER_VOICE_OVERRIDES.items():
        if key in name_lower:
            return voice

    # 3. Infer from spoken line
    if line_text:
        tone = infer_dialogue_tone(line_text)
        if tone in DIALOGUE_TONE_VOICE:
            return DIALOGUE_TONE_VOICE[tone]

    # 4. Scene mood fallback
    if scene_mood:
        mood_lower = scene_mood.lower().strip()
        if mood_lower in MOOD_NARRATOR_VOICE:
            return MOOD_NARRATOR_VOICE[mood_lower]

    return "onyx"  # Default: deep authoritative male


def get_scene_voice_preview(scene: dict, voice_map: dict = None) -> dict:
    """Return voice assignments for a scene — used by the UI."""
    mood = scene.get("mood", "dramatic")
    narrator_voice = get_voice_for_narrator(mood)
    preview = {
        "narrator": {
            "voice": narrator_voice,
            "description": VOICE_DESCRIPTIONS.get(narrator_voice, narrator_voice),
            "reason": f"Mood: {mood}"
        },
        "dialogue": []
    }
    for line in scene.get("dialogue", []):
        speaker = line.get("speaker", "Character")
        text = line.get("line", "")
        # Check bible first for preview
        bible_id = _lookup_bible_voice_id(speaker)
        if bible_id:
            voice = f"bible:{speaker}"
            desc = "Locked in Character Bible"
            reason = "Character Bible (locked)"
        else:
            voice = get_voice_for_character(speaker, text, mood, voice_map)
            desc = VOICE_DESCRIPTIONS.get(voice, voice)
            tone = infer_dialogue_tone(text)
            reason = f"Fallback | Tone: {tone}"
        preview["dialogue"].append({
            "speaker": speaker,
            "voice": voice,
            "description": desc,
            "reason": reason
        })
    return preview


def generate_audio_for_scene(scene: dict, project_name: str,
                              voice_map: dict = None) -> dict:
    """Generate all audio for a scene. Bible voices are absolute."""
    scene_num = scene.get("scene_number", 1)
    scene_mood = scene.get("mood", "dramatic")
    result = {"voiceover": None, "dialogue": []}

    # Voiceover — narrator voice (mood-driven, not character-locked)
    vo_text = scene.get("voiceover", "").strip()
    if vo_text:
        vo_path = AUDIO_DIR / f"{project_name}_s{scene_num:02d}_vo.mp3"
        if not vo_path.exists():
            narrator_voice = get_voice_for_narrator(scene_mood)
            _generate_tts(vo_text, "narrator", str(vo_path),
                          voice_map=voice_map, override_voice=narrator_voice)
        result["voiceover"] = str(vo_path)

    # Dialogue — bible voice is absolute for every character
    for i, line in enumerate(scene.get("dialogue", [])):
        speaker = line.get("speaker", "Character")
        text = line.get("line", "").strip()
        if not text:
            continue
        audio_path = AUDIO_DIR / f"{project_name}_s{scene_num:02d}_d{i:02d}_{speaker.lower()[:8]}.mp3"
        if not audio_path.exists():
            _generate_tts_for_character(text, speaker, str(audio_path),
                                         voice_map=voice_map,
                                         scene_mood=scene_mood,
                                         line_text=text)
        result["dialogue"].append({
            "speaker": speaker,
            "line": text,
            "audio_path": str(audio_path)
        })

    return result


def _generate_tts_for_character(text: str, character: str, output_path: str,
                                  voice_map: dict = None, scene_mood: str = "",
                                  line_text: str = ""):
    """
    Generate TTS for a named character.
    ALWAYS checks bible first. If in bible, uses that voice_id directly.
    Only falls back to tone/mood selection if NOT in bible.
    """
    el_key = os.environ.get("ELEVENLABS_API_KEY", "")

    # ── STEP 1: Check Character Bible (ABSOLUTE PRIORITY) ──
    bible_voice_id = _lookup_bible_voice_id(character)
    if bible_voice_id and el_key:
        try:
            _elevenlabs_tts_by_id(text, character, output_path, bible_voice_id)
            return
        except Exception as e:
            print(f"[TTS] ElevenLabs bible voice failed for {character}: {e}")
            # Fall through to OpenAI with best matching voice

    # ── STEP 2: Non-bible fallback — tone/mood selection ──
    fallback_voice = get_voice_for_character(character, line_text, scene_mood, voice_map)

    if el_key:
        try:
            el_voice_id = ELEVENLABS_VOICE_MAP.get(fallback_voice, ELEVENLABS_VOICE_MAP["onyx"])
            _elevenlabs_tts_by_id(text, character, output_path, el_voice_id)
            return
        except Exception as e:
            print(f"[TTS] ElevenLabs fallback failed for {character}: {e} — trying OpenAI")

    # ── STEP 3: OpenAI TTS fallback ──
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            _openai_tts(text, character, output_path, override_voice=fallback_voice)
            return
        except Exception as e:
            print(f"[TTS] OpenAI TTS failed for {character}: {e}")

    # ── STEP 4: Silent/gTTS fallback ──
    _espeak_tts(text, output_path)


def _generate_tts(text: str, character: str, output_path: str,
                  voice_map: dict = None, override_voice: str = None):
    """Legacy wrapper — used for narrator/voiceover (not character dialogue)."""
    el_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if el_key:
        try:
            el_voice_id = ELEVENLABS_VOICE_MAP.get(
                override_voice or "onyx",
                ELEVENLABS_VOICE_MAP["onyx"]
            )
            _elevenlabs_tts_by_id(text, character, output_path, el_voice_id)
            return
        except Exception as e:
            print(f"[TTS] ElevenLabs failed for {character}: {e} — falling back to OpenAI")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            _openai_tts(text, character, output_path, override_voice=override_voice)
            return
        except Exception as e:
            print(f"[TTS] OpenAI TTS failed for {character}: {e}")
    _espeak_tts(text, output_path)


def _elevenlabs_tts_by_id(text: str, character: str, output_path: str, voice_id: str):
    """Call ElevenLabs API with a specific voice_id directly."""
    import requests as _req
    el_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not el_key:
        raise ValueError("ELEVENLABS_API_KEY not set")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": el_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }
    payload = {
        "text": text[:5000],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.80,
            "style": 0.35,
            "use_speaker_boost": True
        }
    }
    resp = _req.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(resp.content)
    print(f"[TTS/EL] {character:14s} → voice_id:{voice_id[:20]}... | {text[:55]}...")


# Keep old signature for backward compatibility
def _elevenlabs_tts(text: str, character: str, output_path: str,
                    voice_map: dict = None, override_voice: str = None):
    """Backward-compatible wrapper. Checks bible first, then override, then fallback."""
    bible_voice_id = _lookup_bible_voice_id(character)
    if bible_voice_id:
        _elevenlabs_tts_by_id(text, character, output_path, bible_voice_id)
        return
    # Non-bible: use override or fallback
    voice_name = override_voice or get_voice_for_character(character, voice_map=voice_map)
    el_voice_id = ELEVENLABS_VOICE_MAP.get(voice_name, ELEVENLABS_VOICE_MAP["onyx"])
    _elevenlabs_tts_by_id(text, character, output_path, el_voice_id)


def _openai_tts(text: str, character: str, output_path: str,
                voice_map: dict = None, override_voice: str = None):
    voice = override_voice or get_voice_for_character(character, voice_map=voice_map)
    active_client = _get_client()
    response = active_client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text[:4096]
    )
    response.stream_to_file(output_path)
    print(f"[TTS/OAI] {character:12s} → voice:{voice:7s} | {text[:55]}...")


def _espeak_tts(text: str, output_path: str):
    duration = max(2, len(text) // 12)
    success = False
    try:
        from gtts import gTTS
        tts = gTTS(text[:500], lang='en', slow=False)
        tts.save(output_path)
        if Path(output_path).exists() and Path(output_path).stat().st_size > 500:
            success = True
    except Exception:
        pass
    if not success:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=220:duration={duration}",
            "-c:a", "libmp3lame", "-q:a", "4", output_path
        ], capture_output=True)


def build_scene_audio_track(scene: dict, audio_result: dict,
                             project_name: str) -> str:
    scene_num = scene.get("scene_number", 1)
    out_path = AUDIO_DIR / f"{project_name}_s{scene_num:02d}_combined.mp3"
    if out_path.exists():
        return str(out_path)

    parts = []
    if audio_result.get("voiceover"):
        parts.append(audio_result["voiceover"])
    for d in audio_result.get("dialogue", []):
        if d.get("audio_path") and Path(d["audio_path"]).exists():
            parts.append(d["audio_path"])

    if not parts:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=1:duration={scene.get('duration', 5)}",
            "-c:a", "libmp3lame", str(out_path)
        ], capture_output=True)
        return str(out_path)

    if len(parts) == 1:
        import shutil
        shutil.copy(parts[0], str(out_path))
        return str(out_path)

    list_file = AUDIO_DIR / f"{project_name}_s{scene_num:02d}_list.txt"
    with open(list_file, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", str(out_path)
    ], capture_output=True)
    list_file.unlink(missing_ok=True)
    return str(out_path)


if __name__ == "__main__":
    # Quick voice selection test
    test_chars = ["PRESSURE", "GREGORY STARR", "NARRATOR", "AMANI", "MARCUS"]
    print("=== VOICE SELECTION TEST ===\n")
    for char in test_chars:
        bible_id = _lookup_bible_voice_id(char)
        if bible_id:
            print(f"  {char:20s} → BIBLE LOCKED: {bible_id[:25]}...")
        else:
            fallback = get_voice_for_character(char)
            print(f"  {char:20s} → FALLBACK: {fallback}")
