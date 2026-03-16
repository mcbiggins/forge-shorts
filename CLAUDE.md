# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Forge Shorts is a standalone module of The Forge post-production pipeline. It autonomously converts long-form video into vertical YouTube Shorts: video drop → Whisper transcription → Claude segment selection → smart 9:16 cropping via Claude Vision → NVENC GPU encoding → CapCut-style karaoke subtitles (Montserrat Black) → final MP4.

The system runs as a Docker container (`forge-shorts-api`) within the existing Forge Docker stack at `/mnt/md0/docker/projects/clippy/`. The React UI is integrated into the Forge frontend at the `/shorts` route.

## Two Working Directories

- **`/mnt/md0/projects/github/shorts/`** — Python pipeline code + Dockerfile. Edit Python files here.
- **`/mnt/md0/docker/projects/clippy/`** — Docker stack, frontend, nginx. Edit React/UI/compose files here.

After Python changes: `cd /mnt/md0/docker/projects/clippy && docker compose build shorts-api && docker compose up -d shorts-api`
After frontend changes: `cd /mnt/md0/docker/projects/clippy && docker compose build frontend && docker compose up -d frontend`

## Repository Layout

```
/mnt/md0/projects/github/shorts/     ← THIS REPO (Python pipeline + Dockerfile)
├── CLAUDE.md
├── Dockerfile                        ← nvidia/cuda + BtbN FFmpeg + NVENC + Montserrat Black
├── requirements.txt
├── .env                              ← Local dev only; container uses docker-compose env vars
├── config.py                         ← All config, reads from env vars
├── shorts_api.py                     ← FastAPI service (port 5682)
├── presets.py                        ← Content presets (Gaming, Automotive, Interview, etc.)
├── orchestrate.py                    ← Main pipeline (processes one video end-to-end)
├── segment_selector.py               ← Claude API → sequential or montage segments
├── frame_analyzer.py                 ← Claude Vision → smart crop positioning
├── subtitle_generator.py             ← Word timestamps → ASS karaoke file
├── exporter.py                       ← FFmpeg: extract, crop, montage concat, loudnorm, burn
├── transcribe.py                     ← Send video to Whisper, return word-level transcript
├── discover_whisper.py               ← Auto-detect Whisper container endpoint
├── tracker.py                        ← PostgreSQL job + segment tracking
├── cache.py                          ← Transcript + segment result caching
├── watcher.py                        ← Polls inbox folder, dispatches orchestrate.py
├── resolve_builder.py                ← DaVinci Resolve API (optional, not in container)
├── ForgeShorts.jsx                   ← React component (source copy; deployed copy in clippy)
└── routes-shorts.js                  ← DEAD CODE (replaced by shorts_api.py)
```

```
/mnt/md0/docker/projects/clippy/      ← DOCKER STACK (where containers are managed)
├── docker-compose.yml                 ← Defines all services including shorts-api
├── .env                               ← ANTHROPIC_API_KEY + POSTGRES_PASSWORD live here
├── frontend/
│   ├── nginx.conf                     ← Proxies /api/shorts/ → forge-shorts-api:5682
│   ├── vite.config.js                 ← Dev proxy for /api/shorts
│   └── src/
│       ├── App.jsx                    ← Route: /shorts → ForgeShorts
│       ├── components/Layout.jsx      ← Sidebar nav item + conditional wrapper
│       └── pages/ForgeShorts.jsx      ← THE DEPLOYED UI COMPONENT
└── ... (auto-editor/, resolve-api/, postgres/, etc.)
```

## Commands

```bash
# Rebuild shorts API after Python changes
cd /mnt/md0/docker/projects/clippy
docker compose build shorts-api && docker compose up -d shorts-api

# Rebuild frontend after JSX/nginx changes
docker compose build frontend && docker compose up -d frontend

# View shorts API logs
docker logs forge-shorts-api -f --tail 50

# Check all container health
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "forge|clippy"

# Test API health
curl http://192.168.1.11:3000/api/shorts/health

# Clear segment cache (forces re-run of Claude on next process)
find /mnt/clippy -name "segments_*.json" -path "*shorts_cache*" -delete

# Clear ALL caches (forces re-transcription + re-selection)
find /mnt/clippy -name "*.json" -path "*shorts_cache*" -delete
```

## Architecture

### Containerized Service

| Service | Container | Port | Purpose |
|---|---|---|---|
| Shorts API | `forge-shorts-api` | 5682 | FastAPI + pipeline orchestration |
| Whisper ASR | `whisper-asr` | 9050 | Speech-to-text (GPU, separate stack) |
| PostgreSQL | `forge-postgres` | 5432 | Shared with Forge main pipeline |
| Forge Frontend | `forge-frontend` | 3000 | React UI, proxies all APIs via Nginx |

The shorts container has:
- **NVIDIA GPU access** (GPU 1 via `CUDA_VISIBLE_DEVICES=1`) for NVENC encoding
- **BtbN static FFmpeg** with h264_nvenc, hevc_nvenc, av1_nvenc
- **Montserrat Black font** for subtitle rendering
- **Volume mount**: `/mnt/clippy:/mnt/clippy` for NFS video files

### Pipeline Flow

```
POST /process {file: "/mnt/clippy/shorts/video.mp4"}
    ↓
orchestrate.py spawned as subprocess with --settings JSON
    ↓
1. Discover Whisper (host.docker.internal:9050)
2. Transcribe → word-level timestamps (cached after first run)
3. Claude Sonnet 4.6 → segment selection (sequential or montage, cached per clip_style)
4. Per segment:
   a. Claude Vision → smart crop analysis (if framing != center_crop)
   b. FFmpeg NVENC extract + 9:16 crop (or montage: multi-clip + xfade dissolve + concat)
   c. ASS subtitle generation (Montserrat Black, karaoke word highlight)
   d. Loudnorm -14 LUFS (YouTube Shorts spec)
   e. Subtitle burn-in via FFmpeg ass filter + NVENC
5. Move source to shorts_done/
```

### Content Presets

| Preset | Framing | Clip Style | Vision Frames | Cost |
|---|---|---|---|---|
| Gaming | Split Layout | Sequential | 2 | Low |
| Automotive | Smart Frame | Montage | 4 | Medium |
| Interview | Face Track* | Sequential | 3 | Medium |
| Vlogging | Smart Frame | Montage | 4 | Medium |
| How-To | Center Crop | Sequential | 0 | Very Low |

*Face Track currently falls back to Smart Frame (Claude Vision).

### Caching Strategy

- **Transcript**: Saved after Whisper. If cache exists, Whisper is skipped entirely.
- **Segments**: Keyed by clip_style (`segments_sequential.json` / `segments_montage.json`). Reused if transcript is >90% similar. Changing clip_style forces a new Claude call.
- Cache location: `/mnt/clippy/shorts_processing/.shorts_cache/<video_hash>/`

### Runtime Folder Lifecycle

`clippy/shorts/` (inbox) → `clippy/shorts_processing/` (in-flight) → `clippy/shorts_done/` (archived). Outputs: `clippy/shorts_output/`.

### Job Status Lifecycle

```
queued → discovering → transcribing → selecting → building → rendering → exporting → complete
                                                                                    ↘ failed
```

## Configuration

All config injected via docker-compose environment variables.

**Docker-compose `.env`** (`/mnt/md0/docker/projects/clippy/.env`):
```
POSTGRES_PASSWORD=forgedev2026
ANTHROPIC_API_KEY=sk-ant-...
```

**Container env** (docker-compose.yml `shorts-api` service):
- `FORGE_ROOT=/mnt` → inbox becomes `/mnt/clippy/shorts/`
- `PG_DSN=postgresql://forge:...@forge-postgres:5432/forge`
- `WHISPER_HOST=host.docker.internal`, `WHISPER_PORT=9050`
- `CUDA_VISIBLE_DEVICES=1` (GPU 1 for NVENC)

## Key Design Decisions

1. **Container-first** — Runs in Docker, not systemd. Matches Forge architecture, enables remote management.
2. **GPU encoding** — All FFmpeg uses `h264_nvenc` on GPU 1 (RTX 3090).
3. **Smart crop, not letterbox** — 16:9 → 9:16 by cropping, not adding black bars. Claude Vision picks crop position.
4. **Montage with dissolves** — Multi-clip montages use `fadeblack` xfade transitions (0.5s) + audio crossfade.
5. **Subtitle style** — Montserrat Black, size 75 at 1080x1920, 16 chars/line max, MarginV=480 (25% up from bottom), active word yellow 110% scale.
6. **Segment tolerance** — Under-min segments kept (hard floor: 60% of min). Over-max trimmed by shortening/dropping clips.
7. **Claude model** — `claude-sonnet-4-6` for segment selection and vision analysis.
8. **Transcript caching** — Whisper skipped if cached transcript exists. Segments cached per clip_style.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/presets` | Preset definitions + framing/clip mode metadata |
| GET | `/jobs` | All jobs, newest first |
| GET | `/jobs/:id/segments` | Segments for a job |
| GET | `/outputs` | Completed segments with output files |
| GET | `/download/:segmentId` | Stream file download |
| GET | `/files` | Video files in inbox |
| GET | `/settings` | Current settings |
| POST | `/settings` | Update settings (validated: preset, framing, clipStyle, durations) |
| POST | `/process` | Start processing `{file: "/path/to/file"}` |
| POST | `/watcher` | Toggle watcher `{active: true/false}` |

## DB Schema (auto-created by tracker.init_db())

```sql
forge_shorts_jobs (id, source_file, status, created_at, updated_at, error, metadata JSONB)
forge_shorts_segments (id, job_id, segment_index, title, start_sec, end_sec, hook, rationale, status, output_file, created_at)
```

## Coding Conventions

- All config from `config.py` via env vars — never hardcode
- All DB access through `tracker.py` — no raw SQL elsewhere
- `orchestrate.py` catches per-segment exceptions and continues
- Use `logging.getLogger(__name__)` — never bare `print()`
- FFmpeg through `exporter._run()` — never raw subprocess in other modules
- React uses inline styles + `C` design tokens — no CSS modules or Tailwind

## Debugging

```bash
# Container logs
docker logs forge-shorts-api -f --tail 100

# Check jobs
docker exec forge-postgres psql -U forge -d forge -c \
  "SELECT id, source_file, status, error FROM forge_shorts_jobs ORDER BY id DESC LIMIT 10;"

# Fix stuck jobs
docker exec forge-postgres psql -U forge -d forge -c \
  "UPDATE forge_shorts_jobs SET status='failed', error='manual reset' WHERE status NOT IN ('complete','failed','queued');"

# Move stuck file back to inbox
mv /mnt/clippy/shorts_processing/*.mp4 /mnt/clippy/shorts/

# Verify GPU + NVENC
docker exec forge-shorts-api nvidia-smi --query-gpu=name --format=csv,noheader
docker exec forge-shorts-api ffmpeg -encoders 2>/dev/null | grep nvenc

# Verify font
docker exec forge-shorts-api fc-list | grep -i montserrat

# Test Claude API
docker exec forge-shorts-api python3 -c "
import anthropic, os
c = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
r = c.messages.create(model='claude-sonnet-4-6', max_tokens=20, messages=[{'role':'user','content':'hi'}])
print(r.model, r.content[0].text)"
```

## Setting Up on a New Machine

### Prerequisites
- Docker with NVIDIA Container Toolkit
- NVIDIA GPU with NVENC support
- Storage mount at `/mnt/clippy/` (or adjust volume mounts)
- Whisper ASR container accessible from Docker network
- Anthropic API key

### Steps

1. Clone this repo and the clippy stack
2. Set secrets in `clippy/.env`: `POSTGRES_PASSWORD` and `ANTHROPIC_API_KEY`
3. Create directories: `mkdir -p /mnt/clippy/shorts{,_output,_processing,_done}`
4. Build: `cd clippy && docker compose build shorts-api frontend && docker compose up -d`
5. Verify: `curl http://<ip>:3000/api/shorts/health`
6. Browse to `http://<ip>:3000/shorts`

### Hardware Adjustments
- **GPU**: Change `CUDA_VISIBLE_DEVICES` in docker-compose.yml
- **Whisper**: Change `WHISPER_HOST`/`WHISPER_PORT` in docker-compose.yml
- **File paths**: Update volume mounts in docker-compose.yml
