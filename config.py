"""
Forge Shorts — Centralized Configuration
All values override-able via .env in this directory.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── Paths ─────────────────────────────────────────────────────────────────────
FORGE_ROOT       = Path(os.getenv("FORGE_ROOT", "/opt/forge"))
CLIPPY_DIR       = FORGE_ROOT / "clippy"
SHORTS_INBOX     = CLIPPY_DIR / "shorts"           # drop videos here
SHORTS_OUTPUT    = CLIPPY_DIR / "shorts_output"    # finished .mp4s land here
SHORTS_PROCESSING = CLIPPY_DIR / "shorts_processing"
SHORTS_DONE      = CLIPPY_DIR / "shorts_done"

# ── Whisper ───────────────────────────────────────────────────────────────────
WHISPER_HOST     = os.getenv("WHISPER_HOST", "localhost")
WHISPER_PORT     = int(os.getenv("WHISPER_PORT", "9000"))
WHISPER_URL      = os.getenv("WHISPER_URL", "")    # override auto-discovery

# ── DaVinci Resolve ───────────────────────────────────────────────────────────
RESOLVE_HOST     = os.getenv("RESOLVE_PROJECT_SERVER", "192.168.1.16")
RESOLVE_PORT     = int(os.getenv("RESOLVE_PROJECT_PORT", "8543"))
RESOLVE_OUTPUT_DIR = Path(os.getenv("RESOLVE_OUTPUT_DIR", str(FORGE_ROOT / "renders")))
FPS              = float(os.getenv("FPS", "29.97"))

# ── Claude API ────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL     = "claude-sonnet-4-6"

# ── PostgreSQL ────────────────────────────────────────────────────────────────
PG_DSN           = os.getenv("PG_DSN", "postgresql://forge:forge@localhost:5432/forge")

# ── Subtitle Style ────────────────────────────────────────────────────────────
# ASS color format: &HAABBGGRR (alpha, blue, green, red)
SUBTITLE_FONT         = os.getenv("SUBTITLE_FONT", "Montserrat Black")
SUBTITLE_FONT_SIZE    = int(os.getenv("SUBTITLE_FONT_SIZE", "115"))
SUBTITLE_ACTIVE_COLOR = os.getenv("SUBTITLE_ACTIVE_COLOR", "&H0000FFFF")  # yellow
SUBTITLE_BASE_COLOR   = os.getenv("SUBTITLE_BASE_COLOR",   "&H00FFFFFF")  # white
SUBTITLE_OUTLINE_COLOR = os.getenv("SUBTITLE_OUTLINE_COLOR","&H00000000") # black
SUBTITLE_WORDS_PER_GROUP = int(os.getenv("SUBTITLE_WORDS_PER_GROUP", "4"))
SUBTITLE_MAX_CHARS_PER_LINE = int(os.getenv("SUBTITLE_MAX_CHARS_PER_LINE", "16"))
SUBTITLE_MARGIN_V    = int(os.getenv("SUBTITLE_MARGIN_V", "480"))  # ~25% up from bottom

# ── Short Segment Constraints ─────────────────────────────────────────────────
SEGMENT_MIN_DURATION = float(os.getenv("SEGMENT_MIN_DURATION", "30"))   # seconds
SEGMENT_MAX_DURATION = float(os.getenv("SEGMENT_MAX_DURATION", "60"))   # seconds
SEGMENT_TARGET_DURATION = float(os.getenv("SEGMENT_TARGET_DURATION", "45")) # sweet spot
SEGMENT_TARGET_COUNT = int(os.getenv("SEGMENT_TARGET_COUNT", "4"))
