"""
Forge Shorts — Folder Watcher
Polls clippy/shorts/ for new video files and spawns orchestrate.py
as a subprocess for each one.

Run as a daemon:
    python watcher.py

Or with systemd — see the service file in this directory.
"""
import logging
import subprocess
import sys
import time
from pathlib import Path

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] forge.shorts.watcher — %(message)s",
)
log = logging.getLogger("forge.shorts.watcher")

POLL_INTERVAL = 10   # seconds between inbox scans
VIDEO_EXTS    = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
ORCHESTRATOR  = Path(__file__).parent / "orchestrate.py"

# Track files we've already handed off (in case file lingers briefly)
_dispatched: set[Path] = set()


def watch():
    inbox = config.SHORTS_INBOX
    inbox.mkdir(parents=True, exist_ok=True)

    log.info(f"Watching inbox : {inbox}")
    log.info(f"Output dir     : {config.SHORTS_OUTPUT}")
    log.info(f"Poll interval  : {POLL_INTERVAL}s")
    log.info("Ready. Drop videos into the inbox folder.")

    while True:
        try:
            for f in sorted(inbox.iterdir()):
                if (
                    f.is_file()
                    and f.suffix.lower() in VIDEO_EXTS
                    and f not in _dispatched
                ):
                    # Wait briefly to ensure the file is fully written
                    # (handles slow network copies)
                    size_a = f.stat().st_size
                    time.sleep(2)
                    if not f.exists():
                        continue   # removed already
                    size_b = f.stat().st_size
                    if size_a != size_b:
                        log.info(f"File still growing, skipping this cycle: {f.name}")
                        continue

                    log.info(f"New file → dispatching: {f.name}")
                    _dispatched.add(f)

                    subprocess.Popen(
                        [sys.executable, str(ORCHESTRATOR), str(f)],
                        cwd=str(ORCHESTRATOR.parent),
                    )

        except Exception as e:
            log.error(f"Watcher loop error: {e}", exc_info=True)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    watch()
