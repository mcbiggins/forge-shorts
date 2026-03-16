"""
Forge Shorts — Whisper Auto-Discovery
Probes the local network for a running Whisper container and identifies
its API flavor so transcribe.py can call it correctly.

Supported flavors:
  - openai_compat    → /v1/audio/transcriptions  (faster-whisper-server, wyoming-openai, etc.)
  - asr_webservice   → /asr                      (onerahmet/openai-whisper-asr-webservice)
  - faster_whisper   → /transcribe               (Speaches / custom faster-whisper containers)

Run standalone to test: python discover_whisper.py
"""
import sys
import logging
import requests
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

CANDIDATE_PORTS = [9000, 8000, 8080, 10300, 8765]

# (url_path, flavor, label)
PROBES = [
    ("/v1/audio/transcriptions", "openai_compat",  "OpenAI-compat  /v1/audio/transcriptions"),
    ("/asr",                     "asr_webservice",  "ASR Webservice /asr"),
    ("/transcribe",              "faster_whisper",  "Faster-Whisper /transcribe"),
    ("/",                        "unknown",         "Bare root /"),
]


@dataclass
class WhisperEndpoint:
    url: str
    flavor: str
    transcribe_path: str
    word_timestamps: bool

    def __str__(self):
        return f"{self.url}{self.transcribe_path} [{self.flavor}]"


def discover(host: Optional[str] = None, port: Optional[int] = None) -> WhisperEndpoint:
    """
    Auto-discover the Whisper container.
    If host/port are provided, only that target is probed.
    Otherwise, tries localhost on several common ports.
    """
    targets = []

    if host and port:
        targets = [(host, port)]
    elif host:
        targets = [(host, p) for p in CANDIDATE_PORTS]
    elif port:
        targets = [("localhost", port), ("127.0.0.1", port)]
    else:
        targets = [("localhost", p) for p in CANDIDATE_PORTS]
        targets += [("127.0.0.1", p) for p in CANDIDATE_PORTS]

    for (h, p) in targets:
        base = f"http://{h}:{p}"
        for path, flavor, label in PROBES:
            try:
                r = requests.get(f"{base}{path}", timeout=2)
                # 200, 405 (Method Not Allowed), and 422 (Unprocessable Entity)
                # all indicate the route exists — we just GET to probe it.
                if r.status_code in (200, 405, 415, 422):
                    ep = WhisperEndpoint(
                        url=base,
                        flavor=flavor,
                        transcribe_path=path,
                        word_timestamps=True,
                    )
                    log.info(f"Whisper found → {ep}")
                    return ep
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                pass

    raise RuntimeError(
        "Could not auto-discover Whisper container.\n"
        f"Tried hosts/ports: {targets}\n"
        "Set WHISPER_HOST, WHISPER_PORT, or WHISPER_URL in .env to override."
    )


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    host = sys.argv[1] if len(sys.argv) > 1 else None
    port = int(sys.argv[2]) if len(sys.argv) > 2 else None

    try:
        ep = discover(host=host, port=port)
        print(f"\n✓ Whisper endpoint: {ep}")
        print(f"  URL:    {ep.url}")
        print(f"  Path:   {ep.transcribe_path}")
        print(f"  Flavor: {ep.flavor}")
    except RuntimeError as e:
        print(f"\n✗ {e}")
        sys.exit(1)
