"""
Forge Shorts — Orchestrator
End-to-end pipeline for a single source video.

Usage:
    python orchestrate.py /opt/forge/clippy/shorts/myvideo.mp4
    python orchestrate.py /path/to/video.mp4 --settings '{"framing":"smart_frame","clipStyle":"montage"}'

Pipeline:
    1. Discover Whisper container endpoint
    2. Transcribe with word-level timestamps
    3. Select best Short segments via Claude API
    4. Per segment:
       a. Generate ASS karaoke subtitles
       b. Cut via Resolve (or FFmpeg fallback)
       c. Normalize audio (-14 LUFS)
       d. Burn subtitles → final .mp4
    5. Move source to done/
    6. Update PostgreSQL job record throughout
"""
import logging
import subprocess
import sys
from pathlib import Path

import config
import tracker
from tracker import JobStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("forge.shorts")


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_duration(video: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _cleanup(*paths: Path):
    for p in paths:
        try:
            if p and p.exists():
                p.unlink()
        except Exception:
            pass


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process(video_path: Path, settings: dict = None):
    settings = settings or {}
    clip_style = settings.get("clipStyle", "sequential")
    framing = settings.get("framing", "center_crop")
    vision_frames = settings.get("visionFrames", 0)

    log.info(f"{'='*60}")
    log.info(f"Forge Shorts — {video_path.name}")
    log.info(f"Settings: framing={framing}, clipStyle={clip_style}, visionFrames={vision_frames}")
    log.info(f"{'='*60}")

    # Ensure all required directories exist
    for d in [
        config.SHORTS_OUTPUT,
        config.SHORTS_PROCESSING,
        config.SHORTS_DONE,
        config.RESOLVE_OUTPUT_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # Move source to processing immediately (prevents double-pickup by watcher)
    processing_path = config.SHORTS_PROCESSING / video_path.name
    video_path.rename(processing_path)
    video_path = processing_path

    tracker.init_db()
    job_id = tracker.create_job(video_path)

    try:
        # ── 1. Discover Whisper ───────────────────────────────────────────────
        tracker.update_job(job_id, JobStatus.DISCOVERING)
        from discover_whisper import discover
        whisper_ep = discover(
            host=config.WHISPER_HOST if config.WHISPER_HOST != "localhost" else None,
            port=config.WHISPER_PORT if config.WHISPER_PORT != 9000 else None,
        )

        # ── 2. Transcribe (with cache) ───────────────────────────────────────
        tracker.update_job(job_id, JobStatus.TRANSCRIBING)
        from transcribe import transcribe
        import cache

        cached_transcript = cache.load_transcript(video_path)
        if cached_transcript:
            log.info("Using cached transcript (skipping Whisper)")
            transcript = cached_transcript
        else:
            transcript = transcribe(video_path, whisper_ep)
            cache.save_transcript(video_path, transcript)

        duration = get_duration(video_path)
        tracker.update_job(job_id, JobStatus.TRANSCRIBING,
                           metadata={"duration_sec": duration,
                                     "word_count": len(transcript.words),
                                     "language": transcript.language})

        # ── 3. Select segments (cache keyed by clip_style) ───────────────────
        tracker.update_job(job_id, JobStatus.SELECTING)
        from segment_selector import select_segments, Segment, Clip

        cached_segments = cache.load_segments(video_path, clip_style=clip_style)
        if cached_segments and cached_transcript and cache.transcripts_similar(cached_transcript, transcript):
            log.info(f"Reusing cached {clip_style} segments (transcript unchanged)")
            segments = []
            for s in cached_segments:
                clips = []
                if "clips" in s:
                    clips = [Clip(start=c["start"], end=min(c["end"], duration)) for c in s["clips"]]
                if not clips:
                    clips = [Clip(start=s["start"], end=min(s["end"], duration))]
                segments.append(Segment(
                    start=clips[0].start, end=clips[-1].end,
                    title=s["title"], hook=s.get("hook", ""),
                    rationale=s.get("rationale", ""), clips=clips,
                ))
        else:
            segments = select_segments(transcript, duration, clip_style=clip_style, settings=settings)
            cache.save_segments(video_path, segments, clip_style=clip_style)

        if not segments:
            raise RuntimeError("Segment selector returned no valid segments")

        tracker.update_job(job_id, JobStatus.BUILDING,
                           metadata={"segment_count": len(segments)})

        # ── 4. Per-segment processing ─────────────────────────────────────────
        from subtitle_generator import generate_ass
        from exporter import ffmpeg_extract, ffmpeg_extract_montage, normalize_audio, burn_subtitles
        from presets import FRAMING_CENTER_CROP, FRAMING_SMART_FRAME, FRAMING_FACE_TRACK, FRAMING_SPLIT_LAYOUT

        for i, seg in enumerate(segments):
            clip_info = ""
            if seg.is_montage:
                clip_info = f", {len(seg.clips)} clips"
            log.info(f"\n--- Segment {i+1}/{len(segments)}: {seg.title} "
                     f"({seg.duration:.1f}s{clip_info}) ---")

            seg_id = tracker.create_segment(job_id, i, seg)

            try:
                # 4a. Subtitles ────────────────────────────────────────────────
                if seg.is_montage:
                    # For montage: collect words from each clip, adjust timestamps
                    # so they're relative to the concatenated output
                    seg_words = []
                    offset = 0.0
                    for clip in seg.clips:
                        clip_words = [
                            w for w in transcript.words
                            if w.start >= clip.start and w.end <= clip.end
                        ]
                        # Remap word timestamps: source time → concat time
                        from transcribe import Word
                        for w in clip_words:
                            seg_words.append(Word(
                                text=w.text,
                                start=offset + (w.start - clip.start),
                                end=offset + (w.end - clip.start),
                            ))
                        offset += clip.duration
                    ass_path = config.SHORTS_OUTPUT / f"{seg.safe_title}_{i:02d}.ass"
                    generate_ass(seg_words, ass_path, start_offset=0.0)
                else:
                    seg_words = [
                        w for w in transcript.words
                        if w.start >= seg.start and w.end <= seg.end
                    ]
                    ass_path = config.SHORTS_OUTPUT / f"{seg.safe_title}_{i:02d}.ass"
                    generate_ass(seg_words, ass_path, start_offset=seg.start)

                # 4b. Cut — Resolve preferred, FFmpeg fallback ─────────────────
                tracker.update_job(job_id, JobStatus.RENDERING,
                                   metadata={"current_segment": i})

                raw_video = config.SHORTS_OUTPUT / f"{seg.safe_title}_{i:02d}_raw.mp4"

                resolve_used = False
                if not seg.is_montage:
                    try:
                        from resolve_builder import build_and_render, wait_for_render
                        import DaVinciResolveScript as dvr  # type: ignore

                        tl = build_and_render(video_path, seg, i)
                        resolve = dvr.scriptapp("Resolve")
                        project = resolve.GetProjectManager().GetCurrentProject()
                        ok = wait_for_render(project, tl.render_job_id)

                        if ok and tl.output_path.exists():
                            raw_video = tl.output_path
                            resolve_used = True
                        else:
                            log.warning("Resolve render failed — falling back to FFmpeg")

                    except (ImportError, RuntimeError, Exception) as e:
                        log.warning(f"Resolve unavailable ({type(e).__name__}: {e}) "
                                    "— using FFmpeg extraction")

                if not resolve_used:
                    # Determine crop position based on framing mode
                    crop_x, crop_y = 0.5, 0.5  # default center
                    if framing in (FRAMING_SMART_FRAME, FRAMING_SPLIT_LAYOUT,
                                   FRAMING_FACE_TRACK) and vision_frames > 0:
                        try:
                            from frame_analyzer import analyze_frames
                            # Use first clip's time range for analysis
                            an_start = seg.clips[0].start if seg.clips else seg.start
                            an_end = seg.clips[0].end if seg.clips else seg.end
                            analysis = analyze_frames(
                                video_path, an_start, an_end,
                                framing_mode=framing,
                                vision_frames=vision_frames,
                            )
                            crop_x = analysis.crop_x
                            crop_y = analysis.crop_y
                            log.info(f"Frame analysis: crop=({crop_x:.2f}, {crop_y:.2f}) "
                                     f"layout={analysis.layout} facecam={analysis.has_facecam} "
                                     f"— {analysis.reasoning}")
                        except Exception as e:
                            log.warning(f"Frame analysis failed ({e}) — using center crop")

                    if seg.is_montage:
                        ffmpeg_extract_montage(video_path, seg.clips, raw_video,
                                               crop_x=crop_x, crop_y=crop_y)
                    else:
                        ffmpeg_extract(video_path, seg.start, seg.end, raw_video,
                                       crop_x=crop_x, crop_y=crop_y)

                # 4c. Audio normalization ──────────────────────────────────────
                tracker.update_job(job_id, JobStatus.EXPORTING)

                normed = config.SHORTS_OUTPUT / f"{seg.safe_title}_{i:02d}_normed.mp4"
                source_for_burn = normalize_audio(raw_video, normed)

                # 4d. Subtitle burn ────────────────────────────────────────────
                final = config.SHORTS_OUTPUT / f"{seg.safe_title}_{i:02d}_final.mp4"
                burn_subtitles(source_for_burn, ass_path, final)

                # Cleanup intermediates
                _cleanup(normed, raw_video if not resolve_used else None)

                tracker.update_segment(seg_id, "complete", final)
                log.info(f"✓ Short ready → {final.name}")

            except Exception as e:
                log.error(f"Segment {i} ({seg.title}) failed: {e}", exc_info=True)
                tracker.update_segment(seg_id, "failed")
                # Continue processing remaining segments

        # ── 5. Move source to done ────────────────────────────────────────────
        done_path = config.SHORTS_DONE / video_path.name
        video_path.rename(done_path)

        tracker.update_job(job_id, JobStatus.COMPLETE)
        log.info(f"\n{'='*60}")
        log.info(f"Job #{job_id} complete — {len(segments)} shorts in {config.SHORTS_OUTPUT}")
        log.info(f"{'='*60}")

    except Exception as e:
        log.error(f"Job #{job_id} FAILED: {e}", exc_info=True)
        tracker.update_job(job_id, JobStatus.FAILED, error=str(e))
        raise


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json as _json

    if len(sys.argv) < 2:
        print("Usage: python orchestrate.py <video_file> [--settings '{...}']")
        sys.exit(1)

    target = Path(sys.argv[1])
    if not target.exists():
        print(f"File not found: {target}")
        sys.exit(1)

    _settings = None
    if "--settings" in sys.argv:
        idx = sys.argv.index("--settings")
        if idx + 1 < len(sys.argv):
            try:
                _settings = _json.loads(sys.argv[idx + 1])
            except _json.JSONDecodeError:
                log.warning("Could not parse --settings JSON, using defaults")

    process(target, settings=_settings)
