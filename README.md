# Forge Shorts

Autonomous pipeline that converts long-form video into vertical YouTube Shorts. Drop a video file, get back polished 9:16 Shorts with karaoke-style subtitles — no human interaction required.

**Pipeline**: Video drop → Whisper transcription → Claude segment selection → smart 9:16 crop (Claude Vision) → NVENC GPU encoding → CapCut-style karaoke subtitles → final MP4

## Quick Start

### Prerequisites

- Docker with [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- NVIDIA GPU with NVENC support (tested with RTX 3090)
- [Whisper ASR](https://github.com/ahmetoner/whisper-asr-webservice) container running and accessible
- PostgreSQL database (or use the Forge stack's `forge-postgres`)
- [Anthropic API key](https://console.anthropic.com/)

### 1. Pull the Image

The Docker image is published to GitHub Container Registry on every push to `main`.

```bash
docker pull ghcr.io/mcbiggins/forge-shorts:latest
```

### 2. Configure Environment

Create a `.env` file (or set these in your `docker-compose.yml`):

```bash
# ── Required ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...          # Claude API key (segment selection + vision crop)
PG_DSN=postgresql://forge:PASSWORD@forge-postgres:5432/forge  # PostgreSQL connection

# ── Paths ────────────────────────────────────────────────────────────────────
FORGE_ROOT=/mnt                       # Root path — inbox becomes $FORGE_ROOT/clippy/shorts/

# ── Whisper ASR ──────────────────────────────────────────────────────────────
WHISPER_HOST=host.docker.internal     # Hostname of Whisper container
WHISPER_PORT=9050                     # Whisper API port

# ── GPU ──────────────────────────────────────────────────────────────────────
CUDA_VISIBLE_DEVICES=1                # Which GPU for NVENC encoding (0-indexed)
NVIDIA_VISIBLE_DEVICES=all            # Expose all GPU device nodes (required for NVENC)
NVIDIA_DRIVER_CAPABILITIES=compute,video,utility

# ── Optional Overrides ───────────────────────────────────────────────────────
# Segment duration (seconds)
SEGMENT_MIN_DURATION=30               # Hard floor for segment length
SEGMENT_TARGET_DURATION=45            # Claude aims for this duration
SEGMENT_MAX_DURATION=60               # Hard ceiling for segment length
SEGMENT_TARGET_COUNT=4                # Number of Shorts to produce per video

# Subtitle style
SUBTITLE_FONT=Montserrat Black        # Font face (Montserrat Black bundled in image)
SUBTITLE_FONT_SIZE=115                # Font size at PlayResY=1920
SUBTITLE_ACTIVE_COLOR=&H0000FFFF     # Yellow — highlighted word (ASS &HAABBGGRR format)
SUBTITLE_BASE_COLOR=&H00FFFFFF       # White — surrounding words
SUBTITLE_OUTLINE_COLOR=&H00000000    # Black outline
SUBTITLE_WORDS_PER_GROUP=4           # Words visible on screen at once
SUBTITLE_MAX_CHARS_PER_LINE=16       # Max characters per subtitle line
SUBTITLE_MARGIN_V=480                # Vertical margin from bottom (px at 1920 height)

# Whisper auto-discovery override (skip probing)
WHISPER_URL=http://host:port/asr      # Full URL, bypasses auto-discovery

# DaVinci Resolve (optional, not used in container mode)
RESOLVE_PROJECT_SERVER=192.168.1.16
RESOLVE_PROJECT_PORT=8543
FPS=29.97
```

### 3. Create Working Directories

```bash
mkdir -p /mnt/clippy/shorts            # Inbox — drop videos here
mkdir -p /mnt/clippy/shorts_output     # Finished Shorts land here
mkdir -p /mnt/clippy/shorts_processing # Files currently being processed
mkdir -p /mnt/clippy/shorts_done       # Source files archived after completion
```

### 4. Docker Compose

Add to your `docker-compose.yml`:

```yaml
services:
  shorts-api:
    image: ghcr.io/mcbiggins/forge-shorts:latest
    container_name: forge-shorts-api
    restart: unless-stopped
    labels:
      - "com.centurylinklabs.watchtower.enable=true"  # Optional: auto-update via Watchtower
    environment:
      - FORGE_ROOT=/mnt
      - PG_DSN=postgresql://forge:${POSTGRES_PASSWORD}@forge-postgres:5432/forge
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - WHISPER_HOST=host.docker.internal
      - WHISPER_PORT=9050
      - TZ=America/Chicago
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,video,utility
      - CUDA_VISIBLE_DEVICES=1
    runtime: nvidia
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - /mnt/clippy:/mnt/clippy
    ports:
      - "5682:5682"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5682/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

### 5. Start and Verify

```bash
docker compose up -d shorts-api

# Health check
curl http://localhost:5682/health
# → {"status": "ok"}

# Process a video
curl -X POST http://localhost:5682/process \
  -H "Content-Type: application/json" \
  -d '{"file": "/mnt/clippy/shorts/my-video.mp4"}'
```

## Auto-Updates with Watchtower

Watchtower monitors GHCR and auto-deploys new images when you push to `main`.

```yaml
  watchtower:
    image: containrrr/watchtower:latest
    container_name: forge-watchtower
    restart: unless-stopped
    environment:
      - TZ=America/Chicago
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_LABEL_ENABLE=true       # Only update containers with the watchtower label
      - WATCHTOWER_POLL_INTERVAL=300        # Check every 5 minutes
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /root/.docker/config.json:/config.json:ro  # GHCR credentials
```

**GHCR auth** (required on the Docker host):
```bash
# Log Docker into GitHub Container Registry
echo "YOUR_GITHUB_PAT" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

The GitHub PAT needs the `read:packages` scope. Or use `gh auth` if the GitHub CLI is installed:
```bash
gh auth login   # if not already authenticated
cat ~/.config/gh/hosts.yml | grep oauth_token | awk '{print $2}' | docker login ghcr.io -u YOUR_USERNAME --password-stdin
```

## Development Workflow

### Edit → Push → Auto-Deploy

```bash
# 1. Edit Python files in this repo
cd /path/to/forge-shorts
vim segment_selector.py

# 2. Commit and push
git add -A && git commit -m "improve segment targeting" && git push

# 3. GitHub Actions builds the image (~2-3 min)
# 4. Watchtower detects the new image and restarts the container (~5 min)

# Or force immediate deploy:
docker compose pull shorts-api && docker compose up -d shorts-api
```

### Local Dev Build (bypass GHCR)

```bash
# In docker-compose.yml, swap image → build:
#   image: ghcr.io/mcbiggins/forge-shorts:latest   ← comment out
#   build: ./shorts                                  ← uncomment

# Copy source files to build context and build
cp /path/to/forge-shorts/*.py /path/to/clippy-stack/shorts/
docker compose build shorts-api && docker compose up -d shorts-api
```

## API Reference

All endpoints are served on port **5682**. When behind the Forge frontend's Nginx proxy, they're available at `/api/shorts/`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/presets` | Preset definitions + framing/clip mode metadata |
| GET | `/jobs` | All jobs, newest first |
| GET | `/jobs/:id/segments` | Segments for a specific job |
| GET | `/outputs` | Completed segments with output files |
| GET | `/download/:segmentId` | Stream file as download |
| GET | `/files` | Video files in inbox |
| GET | `/settings` | Current runtime settings |
| POST | `/settings` | Update settings `{preset, framing, clipStyle, minDur, targetDur, maxDur}` |
| POST | `/process` | Start processing `{file: "/path/to/file"}` |
| POST | `/watcher` | Toggle folder watcher `{active: true/false}` |

## Pipeline Details

### How It Works

1. **Transcription** — Video audio sent to Whisper ASR for word-level timestamps
2. **Segment Selection** — Full transcript sent to Claude, which identifies the best 30-60s moments based on hook strength, story arc, and payoff
3. **Smart Cropping** — Claude Vision analyzes key frames to determine optimal 9:16 crop position (faces, action, text)
4. **Video Extraction** — FFmpeg with NVENC GPU encoding cuts and crops each segment
5. **Montage Assembly** — For montage-style presets, multiple clips are stitched with crossfade dissolve transitions
6. **Audio Normalization** — Two-pass EBU R128 loudness normalization to -14 LUFS (YouTube Shorts spec)
7. **Subtitle Burn-in** — CapCut-style karaoke subtitles (Montserrat Black, word-by-word highlight) rendered via FFmpeg ASS filter

### Content Presets

| Preset | Framing | Clip Style | Description |
|--------|---------|------------|-------------|
| Gaming | Split Layout | Sequential | Webcam top / gameplay bottom split |
| Automotive | Smart Frame | Montage | Best-of highlights compiled with dissolves |
| Interview | Face Track | Sequential | Follows the speaker |
| Vlogging | Smart Frame | Montage | Multi-moment highlight reel |
| How-To | Center Crop | Sequential | Simple center crop, lowest cost |

### Caching

Results are cached to avoid redundant API calls:

- **Transcript**: Cached after first Whisper call. Subsequent runs skip transcription entirely.
- **Segments**: Keyed by clip style (`segments_sequential.json` / `segments_montage.json`). Changing clip style forces a new Claude call.
- **Cache location**: `shorts_processing/.shorts_cache/<video_hash>/`

Clear caches:
```bash
# Clear segment selections only (re-runs Claude)
find /mnt/clippy -name "segments_*.json" -path "*shorts_cache*" -delete

# Clear everything (re-runs Whisper + Claude)
find /mnt/clippy -name "*.json" -path "*shorts_cache*" -delete
```

### Subtitle Style

CapCut-style karaoke: words appear in groups (default 4). The currently-spoken word is highlighted yellow at 110% scale; surrounding words are white.

- **Font**: Montserrat Black (bundled in Docker image)
- **Size**: 115pt at 1080x1920 resolution (~70% frame width coverage)
- **Outline**: 7px black border for readability
- **Position**: 25% up from bottom (MarginV=480)
- **Color format**: ASS `&HAABBGGRR` (reversed channel order)

### Job Status Lifecycle

```
queued → discovering → transcribing → selecting → building → rendering → exporting → complete
                                                                                    ↘ failed
```

## Database

Uses PostgreSQL (shared with the Forge pipeline). Tables are auto-created on first run.

```sql
forge_shorts_jobs (id, source_file, status, created_at, updated_at, error, metadata JSONB)
forge_shorts_segments (id, job_id, segment_index, title, start_sec, end_sec, hook, rationale, status, output_file, created_at)
```

## Debugging

```bash
# Container logs
docker logs forge-shorts-api -f --tail 100

# Check recent jobs
docker exec forge-postgres psql -U forge -d forge -c \
  "SELECT id, source_file, status, error FROM forge_shorts_jobs ORDER BY id DESC LIMIT 10;"

# Fix stuck jobs
docker exec forge-postgres psql -U forge -d forge -c \
  "UPDATE forge_shorts_jobs SET status='failed', error='manual reset' WHERE status NOT IN ('complete','failed','queued');"

# Move stuck file back to inbox
mv /mnt/clippy/shorts_processing/*.mp4 /mnt/clippy/shorts/

# Verify GPU + NVENC inside container
docker exec forge-shorts-api nvidia-smi --query-gpu=name --format=csv,noheader
docker exec forge-shorts-api ffmpeg -encoders 2>/dev/null | grep nvenc

# Verify font
docker exec forge-shorts-api fc-list | grep -i montserrat

# Test Claude API connectivity
docker exec forge-shorts-api python3 -c "
import anthropic, os
c = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
r = c.messages.create(model='claude-sonnet-4-6', max_tokens=20, messages=[{'role':'user','content':'hi'}])
print(r.model, r.content[0].text)"
```

## File Structure

```
forge-shorts/
├── .github/workflows/build-and-push.yml  ← CI: build + push to GHCR on push to main
├── CLAUDE.md                              ← Claude Code project context
├── README.md                              ← This file
├── Dockerfile                             ← nvidia/cuda 12.6 + BtbN FFmpeg + Montserrat Black
├── requirements.txt                       ← Python dependencies
├── config.py                              ← All config, reads from env vars
├── shorts_api.py                          ← FastAPI service (port 5682)
├── presets.py                             ← Content presets (Gaming, Automotive, etc.)
├── orchestrate.py                         ← Main pipeline (end-to-end processing)
├── segment_selector.py                    ← Claude API → segment selection
├── frame_analyzer.py                      ← Claude Vision → smart crop positioning
├── subtitle_generator.py                  ← Word timestamps → ASS karaoke subtitles
├── exporter.py                            ← FFmpeg: extract, crop, loudnorm, burn-in
├── transcribe.py                          ← Whisper ASR → word-level transcript
├── discover_whisper.py                    ← Auto-detect Whisper endpoint
├── tracker.py                             ← PostgreSQL job/segment tracking
├── cache.py                               ← Transcript + segment result caching
├── watcher.py                             ← Folder watcher (polls inbox)
├── resolve_builder.py                     ← DaVinci Resolve API (optional)
├── ForgeShorts.jsx                        ← React UI component (source copy)
└── routes-shorts.js                       ← Legacy Node routes (replaced by shorts_api.py)
```

## Runtime Directories

```
/mnt/clippy/
├── shorts/              ← Inbox — drop video files here
├── shorts_processing/   ← Files currently being processed
├── shorts_done/         ← Source files archived after completion
└── shorts_output/       ← Finished .mp4 Shorts
```

## License

Private project.
