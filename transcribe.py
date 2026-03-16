"""
Forge Shorts — Whisper Transcription Client
Handles all three API flavors discovered by discover_whisper.py.
Returns a Transcript with per-word timestamps for subtitle generation.
"""
import logging
import requests
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from discover_whisper import WhisperEndpoint

log = logging.getLogger(__name__)

MIME_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".m4v": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Transcript:
    full_text: str
    words: List[Word]
    language: str = "en"
    duration: float = 0.0


def transcribe(video_path: Path, endpoint: WhisperEndpoint) -> Transcript:
    """
    Send video to the Whisper endpoint and return a word-level Transcript.
    Automatically handles all supported API flavors.
    """
    mime = MIME_TYPES.get(video_path.suffix.lower(), "application/octet-stream")
    log.info(f"Transcribing {video_path.name} via {endpoint.flavor} @ {endpoint.url}")

    with open(video_path, "rb") as f:
        if endpoint.flavor == "openai_compat":
            resp = requests.post(
                f"{endpoint.url}/v1/audio/transcriptions",
                files={"file": (video_path.name, f, mime)},
                data={
                    "model": "whisper-1",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                    "language": "en",
                },
                timeout=600,
            )

        elif endpoint.flavor == "asr_webservice":
            resp = requests.post(
                f"{endpoint.url}/asr",
                params={
                    "output": "json",
                    "word_timestamps": "true",
                    "language": "en",
                    "encode": "true",
                },
                files={"audio_file": (video_path.name, f, mime)},
                timeout=600,
            )

        else:  # faster_whisper / unknown
            resp = requests.post(
                f"{endpoint.url}{endpoint.transcribe_path}",
                files={"file": (video_path.name, f, mime)},
                data={"word_timestamps": "true", "language": "en"},
                timeout=600,
            )

    resp.raise_for_status()
    data = resp.json()
    return _parse(data, endpoint.flavor)


def _parse(data: dict, flavor: str) -> Transcript:
    words: List[Word] = []
    text = data.get("text", "").strip()
    lang = data.get("language", "en")

    if flavor == "openai_compat":
        # Words at top level or nested in segments
        raw_words = data.get("words", [])
        if not raw_words:
            for seg in data.get("segments", []):
                raw_words.extend(seg.get("words", []))
        for w in raw_words:
            words.append(Word(
                text=w.get("word", w.get("text", "")).strip(),
                start=float(w["start"]),
                end=float(w["end"]),
            ))

    else:
        # asr_webservice and faster_whisper both nest words inside segments
        for seg in data.get("segments", []):
            for w in seg.get("words", []):
                words.append(Word(
                    text=w.get("word", w.get("text", "")).strip(),
                    start=float(w["start"]),
                    end=float(w["end"]),
                ))

    duration = words[-1].end if words else 0.0
    log.info(f"Transcript: {len(words)} words, {duration:.1f}s, lang={lang}")
    return Transcript(full_text=text, words=words, language=lang, duration=duration)
