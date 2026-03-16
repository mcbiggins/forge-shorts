"""
Forge Shorts — Transcript & Segment Cache
Saves transcription and Claude segment results to JSON files so re-processing
the same (or nearly identical) video doesn't re-incur API costs.

Cache files are stored alongside the source video in the processing directory.
A transcript is considered "same" if the word count differs by less than 10%.
"""
import hashlib
import json
import logging
from pathlib import Path
from typing import List, Optional

from transcribe import Transcript, Word

log = logging.getLogger(__name__)

CACHE_DIR_NAME = ".shorts_cache"


def _cache_dir(video_path: Path) -> Path:
    """Cache directory: parent of video / .shorts_cache / <video_stem_hash>"""
    video_hash = hashlib.md5(video_path.name.encode()).hexdigest()[:12]
    d = video_path.parent / CACHE_DIR_NAME / video_hash
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_transcript(video_path: Path, transcript: Transcript) -> Path:
    """Save transcript to cache. Returns the cache file path."""
    cache = _cache_dir(video_path)
    data = {
        "full_text": transcript.full_text,
        "language": transcript.language,
        "duration": transcript.duration,
        "words": [{"text": w.text, "start": w.start, "end": w.end} for w in transcript.words],
    }
    path = cache / "transcript.json"
    path.write_text(json.dumps(data, indent=2))
    log.info(f"Transcript cached → {path} ({len(transcript.words)} words)")
    return path


def load_transcript(video_path: Path) -> Optional[Transcript]:
    """Load cached transcript if it exists."""
    cache = _cache_dir(video_path)
    path = cache / "transcript.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        words = [Word(text=w["text"], start=w["start"], end=w["end"]) for w in data["words"]]
        t = Transcript(
            full_text=data["full_text"],
            words=words,
            language=data.get("language", "en"),
            duration=data.get("duration", words[-1].end if words else 0.0),
        )
        log.info(f"Transcript loaded from cache ({len(words)} words)")
        return t
    except (json.JSONDecodeError, KeyError) as e:
        log.warning(f"Cache file corrupt, ignoring: {e}")
        return None


def save_segments(video_path: Path, segments: list, clip_style: str = "sequential") -> Path:
    """Save Claude's segment selection to cache. Keyed by clip_style."""
    cache = _cache_dir(video_path)
    data = []
    for s in segments:
        entry = {"start": s.start, "end": s.end, "title": s.title,
                 "hook": s.hook, "rationale": s.rationale}
        if hasattr(s, "clips") and s.clips:
            entry["clips"] = [{"start": c.start, "end": c.end} for c in s.clips]
        data.append(entry)

    filename = f"segments_{clip_style}.json"
    path = cache / filename
    path.write_text(json.dumps(data, indent=2))
    log.info(f"Segments cached → {path} ({len(segments)} segments, style={clip_style})")
    return path


def load_segments(video_path: Path, clip_style: str = "sequential") -> Optional[list]:
    """Load cached segments for a specific clip style."""
    cache = _cache_dir(video_path)
    filename = f"segments_{clip_style}.json"
    path = cache / filename

    # Also check old-style segments.json for backward compat (sequential only)
    if not path.exists() and clip_style == "sequential":
        path = cache / "segments.json"

    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        log.info(f"Segments loaded from cache ({len(data)} segments, style={clip_style})")
        return data
    except (json.JSONDecodeError, KeyError) as e:
        log.warning(f"Segments cache corrupt, ignoring: {e}")
        return None


def transcripts_similar(cached: Transcript, fresh: Transcript, threshold: float = 0.10) -> bool:
    """
    Return True if two transcripts are similar enough to reuse cached segments.
    Compares word count — if within threshold (default 10%), considered the same.
    """
    if not cached.words or not fresh.words:
        return False

    cached_count = len(cached.words)
    fresh_count = len(fresh.words)
    diff = abs(cached_count - fresh_count) / max(cached_count, fresh_count)

    if diff <= threshold:
        log.info(f"Transcripts similar (word diff {diff:.1%} <= {threshold:.0%}) — reusing cached segments")
        return True
    else:
        log.info(f"Transcripts differ (word diff {diff:.1%} > {threshold:.0%}) — re-running Claude")
        return False
