"""
Forge Shorts — Segment Selector
Sends the transcript to Claude and gets back a JSON list of the best
segments for YouTube Shorts. Supports two clip styles:
  - sequential: single continuous clips
  - montage: multiple clips stitched into one Short
"""
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import anthropic

import config
from transcribe import Transcript

log = logging.getLogger(__name__)


@dataclass
class Clip:
    """A single time range within a segment."""
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Segment:
    start: float
    end: float
    title: str
    hook: str
    rationale: str
    clips: List[Clip] = field(default_factory=list)

    @property
    def duration(self) -> float:
        if self.clips:
            return sum(c.duration for c in self.clips)
        return self.end - self.start

    @property
    def is_montage(self) -> bool:
        return len(self.clips) > 1

    @property
    def safe_title(self) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in self.title)


def _sequential_prompt(min_dur: float, target_dur: float, max_dur: float) -> str:
    return (
        "You are an expert short-form video editor who specializes in YouTube Shorts and TikTok.\n"
        "\n"
        "You will receive a video transcript with word-level timestamps.\n"
        "Your job: identify the best segments to cut as standalone YouTube Shorts.\n"
        f"Your PRIMARY target is {target_dur:.0f} seconds. The acceptable range is {min_dur:.0f}\u2013{max_dur:.0f} seconds, but AIM for {target_dur:.0f}.\n"
        f"Do NOT default to {max_dur:.0f}s. Shorter, tighter clips around {target_dur:.0f}s are preferred over longer ones.\n"
        "\n"
        "A great Short has:\n"
        "- A hook in the FIRST 3 SECONDS \u2014 a bold claim, mid-action moment, question, or surprising reveal\n"
        "- A self-contained story arc \u2014 the viewer needs zero context from the rest of the video\n"
        "- A clear payoff, punchline, or resolution at the end\n"
        "- High energy and forward momentum \u2014 no long pauses or meandering setup\n"
        '- Avoids: slow intros, long explanations, "so anyway..." transitions\n'
        "\n"
        "Return ONLY valid JSON. No markdown, no preamble, no explanation outside the array.\n"
        "\n"
        "Format:\n"
        "[\n"
        '  {\n'
        '    "start": 42.1,\n'
        '    "end": 103.7,\n'
        '    "title": "Short_descriptive_slug_for_filename",\n'
        '    "hook": "The exact opening line or action that grabs attention",\n'
        '    "rationale": "One sentence: why this moment works as a Short"\n'
        "  }\n"
        "]"
    )


def _montage_prompt(min_dur: float, target_dur: float, max_dur: float) -> str:
    return (
        "You are an expert short-form video editor who specializes in YouTube Shorts and TikTok.\n"
        "\n"
        "You will receive a video transcript with word-level timestamps.\n"
        "Your job: create MONTAGE Shorts \u2014 each Short is assembled from 2\u20135 clips pulled from\n"
        "DIFFERENT parts of the video, stitched together into one compelling narrative.\n"
        "\n"
        f"CRITICAL: Your PRIMARY target is {target_dur:.0f} seconds total across all clips.\n"
        f"Acceptable range: {min_dur:.0f}\u2013{max_dur:.0f} seconds, but AIM for {target_dur:.0f}.\n"
        f"Do NOT default to {max_dur:.0f}s. Absolute minimum: {min_dur:.0f} seconds.\n"
        "If in doubt, stay close to the target rather than padding to the maximum.\n"
        "\n"
        "A great montage Short:\n"
        "- Opens with a hook clip (bold claim, surprising moment, or question)\n"
        "- Builds a narrative arc across clips \u2014 setup, escalation, payoff\n"
        "- Each individual clip is 8\u201325 seconds (long enough to be coherent)\n"
        f"- 3\u20134 clips per Short is ideal for a {target_dur:.0f}s target\n"
        "- Clips work together to tell a story that no single continuous cut could\n"
        "- Think: best-of highlights, before/after reveals, scattered reactions, thematic compilations\n"
        "\n"
        "Return ONLY valid JSON. No markdown, no preamble.\n"
        "Each Short has a clips array with 2\u20135 time ranges:\n"
        "\n"
        "[\n"
        '  {\n'
        '    "title": "Short_descriptive_slug_for_filename",\n'
        '    "hook": "The opening line or action",\n'
        '    "rationale": "Why these clips together make a great Short",\n'
        '    "clips": [\n'
        '      {"start": 42.1, "end": 58.3},\n'
        '      {"start": 180.5, "end": 198.0},\n'
        '      {"start": 320.0, "end": 338.7}\n'
        "    ]\n"
        "  }\n"
        "]"
    )


def select_segments(
    transcript: Transcript,
    video_duration: float,
    clip_style: str = "sequential",
    settings: dict = None,
) -> List[Segment]:
    """Select segments from transcript. clip_style: 'sequential' or 'montage'."""
    settings = settings or {}
    seg_count = settings.get("segCount", config.SEGMENT_TARGET_COUNT)
    min_dur = settings.get("minDur", config.SEGMENT_MIN_DURATION)
    max_dur = settings.get("maxDur", config.SEGMENT_MAX_DURATION)
    target_dur = settings.get("targetDur", config.SEGMENT_TARGET_DURATION)

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    formatted = _format_for_prompt(transcript)
    is_montage = clip_style == "montage"

    system = (_montage_prompt(min_dur, target_dur, max_dur) if is_montage
              else _sequential_prompt(min_dur, target_dur, max_dur))

    user_msg = (
        f"Video duration: {video_duration:.1f}s\n"
        f"Target: {seg_count} Shorts, "
        f"{min_dur}\u2013{max_dur}s each"
        f"{' (total across clips)' if is_montage else ''}\n\n"
        f"Transcript (grouped by ~10 words with timestamps):\n"
        f"{formatted}\n\n"
        f"Return the best {'montage' if is_montage else ''} segments as JSON."
    )

    log.info(f"Sending transcript to Claude for {'montage' if is_montage else 'sequential'} segment selection...")
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"Claude returned invalid JSON:\n{raw}")
        raise RuntimeError(f"Segment selector JSON parse failed: {e}") from e

    segments = []
    for item in data:
        seg = _parse_segment(item, video_duration, is_montage,
                              min_dur=min_dur, max_dur=max_dur)
        if seg:
            segments.append(seg)

    log.info(f"Claude selected {len(segments)} valid segments ({'montage' if is_montage else 'sequential'})")
    for i, s in enumerate(segments):
        if s.is_montage:
            clip_info = " + ".join(f"{c.start:.1f}-{c.end:.1f}s" for c in s.clips)
            log.info(f"  [{i+1}] {s.title} — {clip_info} (total {s.duration:.1f}s, {len(s.clips)} clips)")
        else:
            log.info(f"  [{i+1}] {s.title} — {s.start:.1f}s\u2192{s.end:.1f}s ({s.duration:.1f}s)")
        log.info(f"       Hook: {s.hook}")

    return segments


def _parse_segment(
    item: dict, video_duration: float, is_montage: bool,
    min_dur: float = 30, max_dur: float = 60,
) -> Optional[Segment]:
    """Parse a single segment from Claude's JSON response. Returns None if invalid."""
    title = item.get("title", "untitled")
    if is_montage and "clips" in item:
        clips = []
        for c in item["clips"]:
            start = float(c["start"])
            end = min(float(c["end"]), video_duration)
            if end > start:
                clips.append(Clip(start=start, end=end))

        if not clips:
            log.warning(f"Skipping montage '{title}': no valid clips")
            return None

        total_dur = sum(c.duration for c in clips)

        # If far too short, skip. Slightly under min is fine — keep it.
        hard_floor = max(15, min_dur * 0.6)
        if total_dur < hard_floor:
            log.warning(f"Skipping montage '{title}': total duration {total_dur:.1f}s < {hard_floor:.0f}s hard floor")
            return None
        if total_dur < min_dur:
            log.info(f"Montage '{title}' is {total_dur:.1f}s (under {min_dur}s target) — keeping anyway")
        if total_dur > max_dur:
            # Trim clips from the end until we fit within max_dur
            for _ in range(len(clips)):  # bounded loop
                current_total = sum(c.duration for c in clips)
                if current_total <= max_dur + 0.5:
                    break
                overshoot = current_total - max_dur
                if overshoot < 1.0:
                    break  # close enough
                last = clips[-1]
                if last.duration > overshoot + 5:
                    clips[-1] = Clip(start=last.start, end=last.end - overshoot)
                    log.info(f"Trimmed montage '{title}' last clip by {overshoot:.1f}s")
                    break
                elif len(clips) > 1:
                    dropped = clips.pop()
                    log.info(f"Dropped montage '{title}' clip {dropped.start:.1f}-{dropped.end:.1f}s to fit")
                else:
                    clips[0] = Clip(start=clips[0].start, end=clips[0].start + max_dur)
                    log.info(f"Trimmed montage '{title}' to {max_dur}s")
                    break

        return Segment(
            start=clips[0].start,
            end=clips[-1].end,
            title=title,
            hook=item.get("hook", ""),
            rationale=item.get("rationale", ""),
            clips=clips,
        )
    else:
        start = float(item.get("start", 0))
        end = min(float(item.get("end", 0)), video_duration)
        dur = end - start

        # For sequential: keep even if slightly off target
        hard_floor = max(15, min_dur * 0.6)
        if dur < hard_floor:
            log.warning(f"Skipping '{title}': duration {dur:.1f}s < {hard_floor:.0f}s hard floor")
            return None
        if dur < min_dur:
            log.info(f"Segment '{title}' is {dur:.1f}s (under {min_dur}s target) — keeping anyway")
        if dur > max_dur:
            # Trim end to fit max
            log.info(f"Trimming '{title}' from {dur:.1f}s to {max_dur}s")
            end = start + max_dur

        return Segment(
            start=start, end=end, title=title,
            hook=item.get("hook", ""),
            rationale=item.get("rationale", ""),
            clips=[Clip(start=start, end=end)],
        )


def _format_for_prompt(transcript: Transcript) -> str:
    """Group words into ~10-word lines with leading timestamp for readability."""
    lines = []
    chunk: list = []
    chunk_start: float | None = None

    for word in transcript.words:
        if chunk_start is None:
            chunk_start = word.start
        chunk.append(word.text)
        if len(chunk) >= 10:
            lines.append(f"[{chunk_start:.1f}s] {' '.join(chunk)}")
            chunk = []
            chunk_start = None

    if chunk and chunk_start is not None:
        lines.append(f"[{chunk_start:.1f}s] {' '.join(chunk)}")

    return "\n".join(lines)
