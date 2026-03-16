"""
Forge Shorts — Frame Analyzer (Claude Vision)
Extracts frames from a video segment and asks Claude Vision where to crop
for optimal 9:16 framing.

Returns a crop position (0.0=left, 0.5=center, 1.0=right) and optional
layout recommendation.
"""
import base64
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List

import anthropic

import config

log = logging.getLogger(__name__)


@dataclass
class FrameAnalysis:
    crop_x: float          # 0.0=left, 0.5=center, 1.0=right
    crop_y: float          # 0.0=top, 0.5=center, 1.0=bottom
    layout: str            # "crop", "split_top_bottom", "center"
    reasoning: str
    has_facecam: bool
    facecam_position: str  # "bottom_left", "bottom_right", "top_left", "top_right", "none"


def extract_frames(video_path: Path, start: float, end: float, count: int = 3) -> List[bytes]:
    """Extract evenly-spaced frames from a segment as JPEG bytes."""
    duration = end - start
    frames = []

    for i in range(count):
        t = start + (duration * (i + 1) / (count + 1))
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
            cmd = [
                "ffmpeg", "-y", "-ss", str(t), "-i", str(video_path),
                "-frames:v", "1", "-q:v", "5",
                "-vf", "scale=640:-1",  # downscale for API efficiency
                tmp.name,
            ]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0:
                frames.append(Path(tmp.name).read_bytes())
            else:
                log.warning(f"Frame extraction failed at {t:.1f}s")

    return frames


def analyze_frames(
    video_path: Path,
    start: float,
    end: float,
    framing_mode: str,
    vision_frames: int = 3,
) -> FrameAnalysis:
    """
    Send frames to Claude Vision for crop/layout analysis.
    Returns a FrameAnalysis with crop position and layout recommendation.
    """
    frames = extract_frames(video_path, start, end, count=vision_frames)

    if not frames:
        log.warning("No frames extracted — defaulting to center crop")
        return FrameAnalysis(
            crop_x=0.5, crop_y=0.5, layout="crop",
            reasoning="No frames available", has_facecam=False, facecam_position="none",
        )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    content = []
    for i, frame_bytes in enumerate(frames):
        b64 = base64.standard_b64encode(frame_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
        content.append({"type": "text", "text": f"Frame {i+1} of {len(frames)}"})

    content.append({"type": "text", "text": (
        "I'm converting this 16:9 video to a 9:16 vertical Short. "
        "Analyze these frames and tell me:\n\n"
        "1. Where is the main visual focus? (left/center/right as a number 0.0-1.0)\n"
        "2. Is there a facecam overlay? If so, where? (bottom_left, bottom_right, top_left, top_right, none)\n"
        "3. What vertical crop position works best? (top/center/bottom as 0.0-1.0)\n"
        "4. Would a split layout work? (full wide shot on top, zoomed detail on bottom)\n\n"
        "Return ONLY valid JSON, no markdown:\n"
        '{"crop_x": 0.5, "crop_y": 0.5, "layout": "crop", '
        '"has_facecam": false, "facecam_position": "none", '
        '"reasoning": "one sentence"}'
    )})

    log.info(f"Sending {len(frames)} frames to Claude Vision for framing analysis...")

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        import json
        data = json.loads(raw)
        return FrameAnalysis(
            crop_x=max(0.0, min(1.0, float(data.get("crop_x", 0.5)))),
            crop_y=max(0.0, min(1.0, float(data.get("crop_y", 0.5)))),
            layout=data.get("layout", "crop"),
            reasoning=data.get("reasoning", ""),
            has_facecam=bool(data.get("has_facecam", False)),
            facecam_position=data.get("facecam_position", "none"),
        )
    except Exception as e:
        log.warning(f"Vision response parse failed ({e}), defaulting to center crop")
        return FrameAnalysis(
            crop_x=0.5, crop_y=0.5, layout="crop",
            reasoning=f"Parse error: {e}", has_facecam=False, facecam_position="none",
        )
