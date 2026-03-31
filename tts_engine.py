"""
ScriptoVision — TTS / Voiceover Engine
Generates audio for voiceovers and character dialogue.
Uses OpenAI TTS (alloy, echo, fable, onyx, nova, shimmer) per character.
Falls back to pyttsx3 / espeak if no API key.
"""

import os
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

# Voice assignments — map character names to OpenAI TTS voices
# Users can override these per-project
DEFAULT_VOICE_MAP = {
    "narrator":  "onyx",    # deep, authoritative
    "default":   "alloy",   # neutral
    "male":      "echo",    # male voice
    "female":    "nova",    # female voice
    "villain":   "fable",   # dramatic
    "child":     "shimmer", # lighter voice
}


def get_voice_for_character(character_name: str, voice_map: dict = None) -> str:
    """Pick the best TTS voice for a character."""
    vm = {**DEFAULT_VOICE_MAP, **(voice_map or {})}
    name_lower = character_name.lower()

    # Direct match
    if name_lower in vm:
        return vm[name_lower]

    # Keyword match
    for keyword, voice in vm.items():
        if keyword in name_lower:
            return voice

    return vm["default"]


def generate_audio_for_scene(scene: dict, project_name: str,
                              voice_map: dict = None) -> dict:
    """
    Generate all audio for a scene: voiceover + all dialogue lines.
    Returns a dict: { "voiceover": path, "dialogue": [{"speaker", "line", "audio_path"}] }
    """
    scene_num = scene.get("scene_number", 1)
    result = {"voiceover": None, "dialogue": []}

    # --- Voiceover ---
    vo_text = scene.get("voiceover", "").strip()
    if vo_text:
        vo_path = AUDIO_DIR / f"{project_name}_s{scene_num:02d}_vo.mp3"
        if not vo_path.exists():
            _generate_tts(vo_text, "narrator", str(vo_path), voice_map)
        result["voiceover"] = str(vo_path)

    # --- Dialogue lines ---
    for i, line in enumerate(scene.get("dialogue", [])):
        speaker = line.get("speaker", "Character")
        text = line.get("line", "").strip()
        if not text:
            continue
        audio_path = AUDIO_DIR / f"{project_name}_s{scene_num:02d}_d{i:02d}_{speaker.lower()[:8]}.mp3"
        if not audio_path.exists():
            _generate_tts(text, speaker, str(audio_path), voice_map)
        result["dialogue"].append({
            "speaker": speaker,
            "line": text,
            "audio_path": str(audio_path)
        })

    return result


def _generate_tts(text: str, character: str, output_path: str,
                  voice_map: dict = None):
    """Generate TTS audio. Uses OpenAI TTS if available, else espeak."""
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if api_key and not api_key.startswith("sk-demo"):
        try:
            _openai_tts(text, character, output_path, voice_map)
        except Exception:
            _espeak_tts(text, output_path)
    else:
        _espeak_tts(text, output_path)


def _openai_tts(text: str, character: str, output_path: str,
                voice_map: dict = None):
    """Use OpenAI TTS API."""
    voice = get_voice_for_character(character, voice_map)
    active_client = _get_client()
    response = active_client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text[:4096]
    )
    response.stream_to_file(output_path)


def _espeak_tts(text: str, output_path: str):
    """Fallback TTS: try gTTS (Google), then silent tone."""
    duration = max(2, len(text) // 12)
    success = False

    # Try gTTS (Google Text-to-Speech via HTTP)
    try:
        from gtts import gTTS
        tts = gTTS(text[:500], lang='en', slow=False)
        tts.save(output_path)
        if Path(output_path).exists() and Path(output_path).stat().st_size > 500:
            success = True
    except Exception:
        pass

    # Last resort: generate a tonal audio file
    if not success:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=220:duration={duration}",
            "-c:a", "libmp3lame", "-q:a", "4", output_path
        ], capture_output=True)


def build_scene_audio_track(scene: dict, audio_result: dict,
                             project_name: str) -> str:
    """
    Combine voiceover + dialogue into a single audio track for the scene.
    Returns path to combined audio file.
    """
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
        # Generate silence
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

    # Concatenate all audio parts
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
    test_scene = {
        "scene_number": 1,
        "voiceover": "It was a hot summer night on the south side of Chicago.",
        "dialogue": [
            {"speaker": "Sub", "line": "Man, these streets got a story to tell."},
            {"speaker": "Friend", "line": "You already know how it goes."}
        ],
        "duration": 6
    }
    result = generate_audio_for_scene(test_scene, "test")
    print(json.dumps(result, indent=2))
