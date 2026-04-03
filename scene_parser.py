"""
ScriptoVision — Scene Parser
Takes a raw script/story and uses GPT to break it into structured scenes
with image prompts, dialogue lines, voiceover text, and motion descriptions.
"""

import os
import json
import re
from openai import OpenAI

def _get_client(key=None):
    """Return an OpenAI client using the real API endpoint."""
    api_key = key or os.environ.get("OPENAI_API_KEY", "")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.openai.com/v1"
    )

client = _get_client()

SYSTEM_PROMPT = """You are a professional film director and AI video production expert.
Your job is to take a script or story and break it into structured video scenes.

For each scene you must output a JSON object with these exact fields:
- "scene_number": integer
- "title": short scene title (5 words max)
- "setting": where the scene takes place (used for image generation)
- "characters": list of character names present
- "image_prompt": a detailed DALL-E image generation prompt that MUST match the visual style specified. Describe lighting, angle, mood, characters, environment — NO text in image.
- "motion_prompt": how the scene should animate (camera movement, subject motion — 1-2 sentences, director style)
- "voiceover": narrator text for this scene (if any, else empty string)
- "dialogue": list of objects with "speaker" and "line" for each spoken line
- "duration": estimated clip duration in seconds (5-10)
- "aspect_ratio": "16:9"
- "mood": one word (e.g. tense, joyful, mysterious, dramatic)

VISUAL STYLE RULES — CRITICAL:
- "cinematic photorealistic": hyper-realistic photography, film grain, cinematic lighting, shallow depth of field, like a Hollywood movie still
- "animated cartoon vibrant": bright vibrant 2D cartoon animation style, bold outlines, expressive characters, like a modern animated TV show or Pixar/Disney style
- "comic book graphic novel": bold ink outlines, halftone dots, high contrast, dramatic angles, like Marvel/DC comics panels
- "anime style detailed": Japanese anime art style, large expressive eyes, detailed backgrounds, cel-shaded, like Studio Ghibli or Demon Slayer
- "dark gritty noir": high contrast black and white or desaturated, dramatic shadows, moody lighting, like a film noir
- "urban street photography": candid street photo style, natural light, documentary feel, authentic urban environments
- "watercolor illustrated": soft watercolor painting style, loose brushstrokes, pastel tones, illustrated book feel

The image_prompt MUST start with the visual style description before describing the scene content.

Other rules:
- Keep scenes focused — one location, one key action per scene
- Dialogue should be natural and match the script exactly
- Motion prompts describe movement, not content (the image handles content)
- If there is no narrator, leave voiceover as empty string
- Return ONLY a valid JSON array of scene objects, no other text
"""

def parse_script_to_scenes(script_text: str, style: str = "cinematic photorealistic",
                           character_references: dict = None,
                           visual_style_prompt: str = None) -> list:
    """
    Send the script to GPT and get back a structured list of scenes.
    character_references: dict of {CHARACTER_NAME: image_reference_prompt}
    visual_style_prompt: DALL-E prefix to enforce consistent style across all scenes
    """
    # Build character consistency block if provided
    char_block = ""
    if character_references:
        char_block = "\n\nCHARACTER VISUAL REFERENCES (MUST include in every scene image_prompt):\n"
        for name, ref in character_references.items():
            char_block += f"- {name}: {ref}\n"
        char_block += "\nEVERY image_prompt MUST include the character's visual reference exactly as written above."

    style_prefix = visual_style_prompt or style

    user_prompt = f"""Visual style: {style}
Style prefix for ALL image_prompts: \"{style_prefix}\"
{char_block}

SCRIPT:
{script_text}

Break this into video scenes. Return a JSON array of scene objects.
Each image_prompt MUST start with \"{style_prefix}\" and include character visual references.
"""
    active_client = _get_client(os.environ.get("OPENAI_API_KEY", ""))
    response = active_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.6,
        max_tokens=4000
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    scenes = json.loads(raw)
    return scenes


def parse_script_demo(script_text: str) -> list:
    """
    Demo parser — uses simple rule-based parsing when no API key is available.
    Splits on blank lines or scene headings.
    """
    scenes = []
    # Split on common scene markers
    blocks = re.split(r'\n{2,}|(?=INT\.|EXT\.|SCENE\s+\d)', script_text.strip())
    blocks = [b.strip() for b in blocks if b.strip()]

    for i, block in enumerate(blocks[:12]):  # cap at 12 scenes
        lines = block.split('\n')
        title_line = lines[0][:50] if lines else f"Scene {i+1}"

        # Extract dialogue lines (lines with a colon like "CHARACTER: text")
        dialogue = []
        voiceover_lines = []
        for line in lines[1:]:
            m = re.match(r'^([A-Z][A-Z\s]+):\s*(.+)', line)
            if m:
                dialogue.append({"speaker": m.group(1).strip().title(), "line": m.group(2).strip()})
            elif line.strip() and not line.isupper():
                voiceover_lines.append(line.strip())

        scenes.append({
            "scene_number": i + 1,
            "title": title_line[:40],
            "setting": "cinematic scene",
            "characters": [],
            "image_prompt": f"Cinematic photorealistic scene: {title_line}. Professional film lighting, shallow depth of field.",
            "motion_prompt": "Camera slowly pushes in, natural motion, cinematic atmosphere.",
            "voiceover": " ".join(voiceover_lines[:3]),
            "dialogue": dialogue,
            "duration": 6,
            "aspect_ratio": "16:9",
            "mood": "dramatic"
        })

    return scenes


if __name__ == "__main__":
    # Quick test
    test_script = """
Scene 1 - The Beginning
It was a hot summer night on the south side of Chicago.
NARRATOR: The wild hundreds never sleep.

Scene 2 - The Streets
SUB: Man, these streets got a story to tell.
FRIEND: You already know how it goes.
"""
    import os
    if os.environ.get("OPENAI_API_KEY"):
        scenes = parse_script_to_scenes(test_script)
    else:
        scenes = parse_script_demo(test_script)
    print(json.dumps(scenes, indent=2))
