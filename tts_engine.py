"""
ScriptoVision — TTS / Voiceover Engine v2
Tone-aware voice selection: reads scene mood, genre, and character type
to automatically assign the best-matching voice for every line.

OpenAI TTS voices:
  alloy   — neutral, versatile
  echo    — male, clear, conversational
  fable   — expressive, storytelling, theatrical
  onyx    — deep, authoritative, commanding (Morgan Freeman-esque)
  nova    — female, warm, natural
  shimmer — female, lighter, youthful
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

# Narrator voice changes based on the scene mood
MOOD_NARRATOR_VOICE = {
    "dramatic":    "onyx",
    "tense":       "onyx",
    "dark":        "onyx",
    "noir":        "onyx",
    "serious":     "onyx",
    "gritty":      "onyx",
    "intense":     "onyx",
    "melancholy":  "onyx",
    "somber":      "onyx",
    "suspenseful": "onyx",
    "emotional":   "fable",
    "nostalgic":   "fable",
    "reflective":  "fable",
    "hopeful":     "fable",
    "inspiring":   "fable",
    "bittersweet": "fable",
    "poetic":      "fable",
    "mysterious":  "fable",
    "action":      "echo",
    "exciting":    "echo",
    "energetic":   "echo",
    "confident":   "echo",
    "bold":        "echo",
    "playful":     "shimmer",
    "comedic":     "shimmer",
    "funny":       "shimmer",
    "lighthearted":"shimmer",
    "joyful":      "nova",
    "romantic":    "nova",
    "warm":        "nova",
    "default":     "onyx",
}

# Named character overrides — always consistent
CHARACTER_VOICE_OVERRIDES = {
    "sub":         "onyx",
    "sernard":     "onyx",
    "narrator":    "onyx",
    "vo":          "onyx",
    "voiceover":   "onyx",
    "villain":     "fable",
    "antagonist":  "fable",
    "boss":        "onyx",
    "detective":   "onyx",
    "officer":     "onyx",
    "cop":         "onyx",
    "soldier":     "onyx",
    "elder":       "onyx",
    "grandfather": "onyx",
    "father":      "echo",
    "dad":         "echo",
    "brother":     "echo",
    "friend":      "echo",
    "homie":       "echo",
    "dj":          "echo",
    "host":        "echo",
    "announcer":   "echo",
    "reporter":    "alloy",
    "teacher":     "alloy",
    "doctor":      "alloy",
    "mother":      "nova",
    "mom":         "nova",
    "sister":      "nova",
    "girl":        "nova",
    "woman":       "nova",
    "lady":        "nova",
    "child":       "shimmer",
    "kid":         "shimmer",
    "boy":         "shimmer",
    "young":       "shimmer",
}

# Tone keywords for inferring dialogue emotion
TONE_KEYWORDS = {
    "aggressive": [
        "get out", "back off", "don't", "stop", "never", "i'll kill",
        "shut up", "move", "now!", "i said", "you better",
        "come at me", "run", "watch yourself", "i'm warning"
    ],
    "angry": [
        "how dare", "i can't believe", "this is ridiculous", "unbelievable",
        "you always", "you never", "i'm done", "enough", "forget it"
    ],
    "commanding": [
        "listen up", "everybody", "attention", "fall in", "stand down",
        "move out", "let's go", "on my signal", "do it now", "execute"
    ],
    "caring": [
        "i love you", "are you okay", "i'm here", "don't worry",
        "i've got you", "you matter", "i care", "be safe", "come home"
    ],
    "gentle": [
        "it's okay", "take your time", "breathe", "relax", "easy now",
        "no rush", "you're safe", "i understand"
    ],
    "sarcastic": [
        "oh sure", "right", "yeah right", "of course", "wow thanks",
        "great idea", "brilliant", "oh really", "sure thing"
    ],
    "excited": [
        "yes!", "let's go!", "finally!", "i can't believe it!", "amazing!",
        "this is it!", "we did it!", "no way!", "oh my god"
    ],
    "playful": [
        "haha", "lol", "you're funny", "gotcha", "bet", "for real though",
        "come on", "stop playing", "you wild"
    ],
}

DIALOGUE_TONE_VOICE = {
    "aggressive":  "onyx",
    "angry":       "onyx",
    "commanding":  "onyx",
    "caring":      "nova",
    "gentle":      "nova",
    "sarcastic":   "fable",
    "excited":     "shimmer",
    "playful":     "shimmer",
    "neutral":     "alloy",
    "default":     "alloy",
}

VOICE_DESCRIPTIONS = {
    "onyx":    "Deep & Authoritative (Morgan Freeman-esque)",
    "echo":    "Clear Male, Conversational",
    "fable":   "Expressive Storyteller, Theatrical",
    "nova":    "Warm Female, Natural",
    "shimmer": "Light Female, Youthful",
    "alloy":   "Neutral, Versatile",
}


def infer_dialogue_tone(line_text: str) -> str:
    """Infer the emotional tone of a spoken line from its text content."""
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
    """Pick narrator voice based on scene mood."""
    mood_lower = (mood or "default").lower().strip()
    return MOOD_NARRATOR_VOICE.get(mood_lower, MOOD_NARRATOR_VOICE["default"])


def get_voice_for_character(character_name: str, line_text: str = "",
                             scene_mood: str = "", voice_map: dict = None) -> str:
    """
    Multi-level tone-aware voice selection:
    1. User voice_map override
    2. Named character override
    3. Dialogue tone inference from line text
    4. Scene mood fallback
    5. Default: alloy
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

    # 2. Named character override
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
            mood_voice = MOOD_NARRATOR_VOICE[mood_lower]
            if mood_voice == "onyx" and name_lower not in ["narrator", "sub", "vo"]:
                return "echo"
            return mood_voice

    return "alloy"


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
        voice = get_voice_for_character(speaker, text, mood, voice_map)
        tone = infer_dialogue_tone(text)
        preview["dialogue"].append({
            "speaker": speaker,
            "voice": voice,
            "description": VOICE_DESCRIPTIONS.get(voice, voice),
            "reason": f"Character: {speaker} | Tone: {tone}"
        })
    return preview


def generate_audio_for_scene(scene: dict, project_name: str,
                              voice_map: dict = None) -> dict:
    """Generate all audio for a scene with tone-aware voice selection."""
    scene_num = scene.get("scene_number", 1)
    scene_mood = scene.get("mood", "dramatic")
    result = {"voiceover": None, "dialogue": []}

    # Voiceover — mood-driven narrator voice
    vo_text = scene.get("voiceover", "").strip()
    if vo_text:
        vo_path = AUDIO_DIR / f"{project_name}_s{scene_num:02d}_vo.mp3"
        if not vo_path.exists():
            narrator_voice = get_voice_for_narrator(scene_mood)
            _generate_tts(vo_text, "narrator", str(vo_path),
                          voice_map=voice_map, override_voice=narrator_voice)
        result["voiceover"] = str(vo_path)

    # Dialogue — full tone-aware per line
    for i, line in enumerate(scene.get("dialogue", [])):
        speaker = line.get("speaker", "Character")
        text = line.get("line", "").strip()
        if not text:
            continue
        audio_path = AUDIO_DIR / f"{project_name}_s{scene_num:02d}_d{i:02d}_{speaker.lower()[:8]}.mp3"
        if not audio_path.exists():
            voice = get_voice_for_character(
                character_name=speaker,
                line_text=text,
                scene_mood=scene_mood,
                voice_map=voice_map
            )
            _generate_tts(text, speaker, str(audio_path),
                          voice_map=voice_map, override_voice=voice)
        result["dialogue"].append({
            "speaker": speaker,
            "line": text,
            "audio_path": str(audio_path)
        })

    return result


def _generate_tts(text: str, character: str, output_path: str,
                  voice_map: dict = None, override_voice: str = None):
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key and not api_key.startswith("sk-demo"):
        try:
            _openai_tts(text, character, output_path,
                        voice_map=voice_map, override_voice=override_voice)
            return
        except Exception as e:
            print(f"[TTS] OpenAI TTS failed for {character}: {e}")
    _espeak_tts(text, output_path)


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
    print(f"[TTS] {character:12s} → voice:{voice:7s} | mood-matched | {text[:55]}...")


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
    test_scenes = [
        {
            "scene_number": 1, "mood": "dramatic",
            "voiceover": "It was the summer of '94, and the streets of Roseland never slept.",
            "dialogue": [
                {"speaker": "Narrator", "line": "The wild hundreds. Where legends were born."},
                {"speaker": "Sub", "line": "Man, these streets got a story to tell."},
                {"speaker": "Friend", "line": "You already know how it goes."},
            ]
        },
        {
            "scene_number": 2, "mood": "tense",
            "voiceover": "The confrontation nobody saw coming.",
            "dialogue": [
                {"speaker": "Villain", "line": "BACK OFF. I'm warning you right now."},
                {"speaker": "Sub", "line": "I'm not going anywhere."},
                {"speaker": "Officer", "line": "Everybody freeze! Get on the ground!"},
            ]
        },
        {
            "scene_number": 3, "mood": "nostalgic",
            "voiceover": "Some things you never forget.",
            "dialogue": [
                {"speaker": "Mother", "line": "I love you. Be safe out there."},
                {"speaker": "Sub", "line": "I will, Ma. I promise."},
                {"speaker": "Kid", "line": "Can I come with you?"},
            ]
        },
    ]
    print("=== TONE-AWARE VOICE SELECTION ===\n")
    for scene in test_scenes:
        preview = get_scene_voice_preview(scene)
        print(f"Scene {scene['scene_number']} — Mood: {scene['mood']}")
        print(f"  Narrator  → {preview['narrator']['voice']:7s} ({preview['narrator']['description']})")
        for d in preview["dialogue"]:
            print(f"  {d['speaker']:12s} → {d['voice']:7s} ({d['description']}) | {d['reason']}")
        print()
