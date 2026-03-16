"""
Forge Shorts — ASS Subtitle Generator
Produces CapCut-style karaoke subtitles: a group of words is visible at once,
and the currently-spoken word is highlighted in yellow at 110% scale.

Output format: SubStation Alpha v4+ (.ass) — burned in by FFmpeg post-render.

ASS color format: &HAABBGGRR
  Yellow = &H0000FFFF   White = &H00FFFFFF   Black = &H00000000
"""
import logging
from pathlib import Path
from typing import List

import config
from transcribe import Word

log = logging.getLogger(__name__)

# ── ASS Header Template ───────────────────────────────────────────────────────
_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{base},{active},{outline},&H80000000,0,0,0,0,100,100,1,0,1,7,2,2,60,60,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    """Seconds → ASS timestamp  H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = round((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _group_words(words: List[Word], max_words: int, max_chars: int) -> List[List[Word]]:
    """Group words respecting both max word count and max character limit per line."""
    groups: List[List[Word]] = []
    current: List[Word] = []
    current_chars = 0

    for w in words:
        word_len = len(w.text.strip())
        # +1 for space separator (except first word)
        new_chars = current_chars + word_len + (1 if current else 0)

        if current and (len(current) >= max_words or new_chars > max_chars):
            groups.append(current)
            current = [w]
            current_chars = word_len
        else:
            current.append(w)
            current_chars = new_chars

    if current:
        groups.append(current)

    return groups


def generate_ass(
    words: List[Word],
    output_path: Path,
    start_offset: float = 0.0,
    words_per_group: int | None = None,
) -> Path:
    """
    Write a .ass file with CapCut-style word highlighting.

    Args:
        words:           Word-level timestamps (absolute time from video start)
        output_path:     Where to write the .ass file
        start_offset:    Segment start time — subtracted from all timestamps
                         so the .ass clock starts at 0:00:00.00
        words_per_group: Words visible at once (default from config)
    """
    wpg = words_per_group or config.SUBTITLE_WORDS_PER_GROUP
    max_chars = config.SUBTITLE_MAX_CHARS_PER_LINE

    if not words:
        log.warning("No words provided to subtitle generator — writing empty .ass")
        output_path.write_text(_header() + "", encoding="utf-8-sig")
        return output_path

    header = _header()
    events: List[str] = []

    # Group words respecting both word count and character limit
    groups = _group_words(words, wpg, max_chars)

    for group in groups:
        group_start_abs = group[0].start
        group_end_abs = group[-1].end

        # For each word in the group, emit one Dialogue event:
        #   - active word  → active_color + 110% scale
        #   - other words  → base_color + 100% scale
        for active_idx, active_word in enumerate(group):
            ev_start = active_word.start - start_offset
            ev_end = active_word.end - start_offset

            # Skip events that fall before clip start
            if ev_end <= 0:
                continue
            ev_start = max(0.0, ev_start)

            # Pad very short word events so the subtitle is readable
            if ev_end - ev_start < 0.05:
                ev_end = ev_start + 0.05

            parts: List[str] = []
            for j, w in enumerate(group):
                clean = w.text.strip()
                if not clean:
                    continue
                if j == active_idx:
                    # Active: yellow + bump scale
                    parts.append(
                        f"{{\\c{config.SUBTITLE_ACTIVE_COLOR}"
                        f"\\fscx110\\fscy110\\b1}}"
                        f"{clean.upper()}"
                        f"{{\\c{config.SUBTITLE_BASE_COLOR}"
                        f"\\fscx100\\fscy100\\b0}}"
                    )
                else:
                    parts.append(clean.upper())

            line = " ".join(parts)

            events.append(
                f"Dialogue: 0,"
                f"{_ts(ev_start)},"
                f"{_ts(ev_end)},"
                f"Default,,0,0,0,,{line}"
            )

    ass_content = header + "\n".join(events)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(ass_content, encoding="utf-8-sig")
    log.info(f"ASS subtitles written → {output_path}  ({len(events)} events)")
    return output_path


def _header() -> str:
    return _HEADER.format(
        font=config.SUBTITLE_FONT,
        size=config.SUBTITLE_FONT_SIZE,
        base=config.SUBTITLE_BASE_COLOR,
        active=config.SUBTITLE_ACTIVE_COLOR,
        outline=config.SUBTITLE_OUTLINE_COLOR,
        marginv=config.SUBTITLE_MARGIN_V,
    )
