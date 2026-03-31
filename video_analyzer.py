"""
ScriptoVision — Video Analyzer & Series Continuation Engine
Analyzes an uploaded video to extract: characters, visual style, tone,
story summary, and episode structure — then generates the next episode script.
"""

import os
import json
import subprocess
import re
from pathlib import Path
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

TEMP_DIR  = Path("/home/ubuntu/scriptovision/temp")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Extract audio transcript from video
# ─────────────────────────────────────────────────────────────────────────────

def extract_audio_from_video(video_path: str) -> str:
    """Extract audio track from video as MP3 for transcription."""
    audio_path = TEMP_DIR / (Path(video_path).stem + "_audio.mp3")
    if audio_path.exists():
        return str(audio_path)

    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "libmp3lame", "-q:a", "4",
        str(audio_path)
    ], capture_output=True, check=True)
    return str(audio_path)


def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio using OpenAI Whisper."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return "[Transcription unavailable — add OpenAI API key]"

    with open(audio_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text"
        )
    return transcript


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Extract video frames for visual analysis
# ─────────────────────────────────────────────────────────────────────────────

def extract_frames(video_path: str, num_frames: int = 8) -> list:
    """Extract evenly-spaced frames from video for visual analysis."""
    frames_dir = TEMP_DIR / (Path(video_path).stem + "_frames")
    frames_dir.mkdir(exist_ok=True)

    # Get video duration
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ], capture_output=True, text=True)

    try:
        duration = float(result.stdout.strip())
    except Exception:
        duration = 60.0

    interval = duration / (num_frames + 1)
    frame_paths = []

    for i in range(1, num_frames + 1):
        timestamp = interval * i
        frame_path = frames_dir / f"frame_{i:02d}.jpg"
        if not frame_path.exists():
            subprocess.run([
                "ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path,
                "-vframes", "1", "-q:v", "2", str(frame_path)
            ], capture_output=True)
        if frame_path.exists():
            frame_paths.append(str(frame_path))

    return frame_paths


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: AI Analysis — extract show bible from transcript + frames
# ─────────────────────────────────────────────────────────────────────────────

def analyze_video_content(transcript: str, video_path: str,
                           show_title: str = "The Show") -> dict:
    """
    Use GPT to analyze the transcript and build a 'show bible' —
    characters, style, tone, story summary, episode structure.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if api_key:
        return _gpt_analyze(transcript, show_title)
    else:
        return _demo_analyze(transcript, show_title)


def _gpt_analyze(transcript: str, show_title: str) -> dict:
    """Use GPT-4 to extract a full show bible from the transcript."""

    system = """You are a professional TV show analyst and story bible creator.
Analyze the provided transcript and extract a complete show bible as JSON with these fields:

{
  "show_title": "string",
  "genre": "string (e.g. comedy, drama, animation, web series)",
  "tone": "string (e.g. lighthearted, gritty, inspirational, comedic)",
  "visual_style": "string (describe the look — animation style, cinematography, color palette)",
  "setting": "string (where the show takes place)",
  "episode_summary": "string (what happened in this episode, 3-5 sentences)",
  "story_arc": "string (the bigger ongoing story across episodes)",
  "cliffhanger": "string (how this episode ended or what was left unresolved)",
  "characters": [
    {
      "name": "string",
      "role": "string (main/supporting/recurring)",
      "description": "string (appearance, personality, speech style)",
      "voice_style": "string (how they talk — accent, tone, catchphrases)",
      "relationships": "string (how they relate to other characters)"
    }
  ],
  "recurring_locations": ["list of places that appear in the show"],
  "themes": ["list of recurring themes or messages"],
  "episode_format": "string (typical episode structure, length, format)",
  "next_episode_hook": "string (a compelling idea for the next episode based on the story so far)"
}

Return ONLY valid JSON, no other text."""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Show title: {show_title}\n\nTranscript:\n{transcript[:6000]}"}
        ],
        temperature=0.5,
        max_tokens=2000
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _demo_analyze(transcript: str, show_title: str) -> dict:
    """Demo analysis when no API key is available."""
    # Extract character names from transcript (lines like "NAME: dialogue")
    characters = []
    seen = set()
    for match in re.finditer(r'^([A-Z][A-Z\s]{2,20}):', transcript, re.MULTILINE):
        name = match.group(1).strip().title()
        if name not in seen and len(name) > 2:
            seen.add(name)
            characters.append({
                "name": name,
                "role": "main",
                "description": f"{name} — character detected from transcript",
                "voice_style": "natural conversational",
                "relationships": "part of the main cast"
            })

    return {
        "show_title": show_title,
        "genre": "web series",
        "tone": "engaging",
        "visual_style": "cinematic, vibrant colors, dynamic camera work",
        "setting": "urban environment",
        "episode_summary": f"Episode of {show_title} analyzed from uploaded video.",
        "story_arc": "Ongoing story following the main characters through their adventures.",
        "cliffhanger": "The episode ends with an unresolved situation that sets up the next chapter.",
        "characters": characters or [
            {"name": "Main Character", "role": "main",
             "description": "The central character of the show",
             "voice_style": "confident and expressive",
             "relationships": "leads the group"}
        ],
        "recurring_locations": ["Main location", "Secondary location"],
        "themes": ["friendship", "adventure", "growth"],
        "episode_format": "Short-form web series episode, 3-8 minutes",
        "next_episode_hook": f"In the next episode of {show_title}, the characters face a new challenge that tests their bonds."
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Generate the next episode script from the show bible
# ─────────────────────────────────────────────────────────────────────────────

def generate_next_episode(show_bible: dict, episode_number: int = 2,
                           user_direction: str = "") -> str:
    """
    Generate a full script for the next episode based on the show bible.
    Returns a formatted script string ready for the scene parser.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if api_key:
        return _gpt_generate_episode(show_bible, episode_number, user_direction)
    else:
        return _demo_generate_episode(show_bible, episode_number)


def _gpt_generate_episode(show_bible: dict, episode_number: int,
                           user_direction: str) -> str:
    """Use GPT to write the next episode script."""

    characters_desc = "\n".join([
        f"- {c['name']} ({c['role']}): {c['description']}. Voice: {c['voice_style']}"
        for c in show_bible.get("characters", [])
    ])

    system = f"""You are a professional TV writer for the show "{show_bible.get('show_title', 'The Show')}".

SHOW BIBLE:
- Genre: {show_bible.get('genre', 'web series')}
- Tone: {show_bible.get('tone', 'engaging')}
- Visual Style: {show_bible.get('visual_style', 'cinematic')}
- Setting: {show_bible.get('setting', 'urban')}
- Story Arc: {show_bible.get('story_arc', '')}
- Previous Episode: {show_bible.get('episode_summary', '')}
- Cliffhanger: {show_bible.get('cliffhanger', '')}
- Themes: {', '.join(show_bible.get('themes', []))}

CHARACTERS:
{characters_desc}

Write a complete script for Episode {episode_number}.
Format it as a proper screenplay:
- Scene headings in ALL CAPS (e.g. INT. LOCATION - DAY)
- Action lines as regular paragraphs
- Character dialogue as: CHARACTER NAME: "dialogue line"
- Narrator lines as: NARRATOR: "narration text"
- Include 4-8 scenes
- Keep each scene focused and punchy
- End with a hook for the next episode
- Match the tone and style of the show exactly
- Use the characters' established voices and speech patterns"""

    direction_note = f"\n\nCreator direction for this episode: {user_direction}" if user_direction else ""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Write Episode {episode_number} of {show_bible.get('show_title', 'The Show')}.{direction_note}"}
        ],
        temperature=0.8,
        max_tokens=3000
    )

    return response.choices[0].message.content.strip()


def _demo_generate_episode(show_bible: dict, episode_number: int) -> str:
    """Generate a demo episode script when no API key is available."""
    title = show_bible.get("show_title", "The Show")
    chars = show_bible.get("characters", [{"name": "Character 1"}, {"name": "Character 2"}])
    c1 = chars[0]["name"] if chars else "Character 1"
    c2 = chars[1]["name"] if len(chars) > 1 else "Character 2"
    setting = show_bible.get("setting", "the city")
    hook = show_bible.get("next_episode_hook", "A new adventure begins.")

    return f"""EPISODE {episode_number} — {title.upper()}

INT. MAIN LOCATION - DAY

NARRATOR: "Last time on {title}... things got interesting. Now the story continues."

{c1.upper()}: "Alright, we gotta figure this out."

{c2.upper()}: "You always say that. What's the plan this time?"

{c1.upper()}: "I'm working on it. Just trust me."

EXT. {setting.upper()} - CONTINUOUS

NARRATOR: "The crew heads out into {setting}, not knowing what's waiting for them."

{c1.upper()}: "You see that? Something's different today."

{c2.upper()}: "Yeah... I feel it too."

INT. MAIN LOCATION - LATER

NARRATOR: "After everything they've been through, one thing is clear — this is just the beginning."

{c1.upper()}: "Whatever comes next, we handle it together."

{c2.upper()}: "Always."

NARRATOR: "{hook}"

FADE OUT.
"""


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE: video → show bible → next episode script
# ─────────────────────────────────────────────────────────────────────────────

def analyze_and_continue(video_path: str, show_title: str = "",
                          episode_number: int = None,
                          user_direction: str = "") -> dict:
    """
    Full pipeline: video file → show bible → next episode script.
    Returns dict with show_bible and next_episode_script.
    """
    if not show_title:
        show_title = Path(video_path).stem.replace("_", " ").title()

    print(f"[ScriptoVision] Analyzing: {show_title}")

    # Extract & transcribe audio
    print("[ScriptoVision] Extracting audio...")
    try:
        audio_path = extract_audio_from_video(video_path)
        print("[ScriptoVision] Transcribing...")
        transcript = transcribe_audio(audio_path)
    except Exception as e:
        print(f"[ScriptoVision] Audio extraction failed: {e}")
        transcript = ""

    # Analyze content
    print("[ScriptoVision] Analyzing characters and story...")
    show_bible = analyze_video_content(transcript, video_path, show_title)

    # Determine next episode number
    if episode_number is None:
        episode_number = 2  # default: assume uploaded is ep 1

    # Generate next episode
    print(f"[ScriptoVision] Writing Episode {episode_number}...")
    next_script = generate_next_episode(show_bible, episode_number, user_direction)

    return {
        "show_title": show_title,
        "show_bible": show_bible,
        "next_episode_number": episode_number,
        "next_episode_script": next_script,
        "transcript": transcript
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = analyze_and_continue(sys.argv[1])
        print("\n=== SHOW BIBLE ===")
        print(json.dumps(result["show_bible"], indent=2))
        print("\n=== NEXT EPISODE SCRIPT ===")
        print(result["next_episode_script"])
