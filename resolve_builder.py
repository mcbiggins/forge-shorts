"""
Forge Shorts — DaVinci Resolve Timeline Builder
Creates a Resolve project and timeline for each Short segment,
queues a render, and waits for completion.

Requires DaVinciResolveScript to be importable — this means the script
must run on the same host as Resolve (or with PYTHONPATH/env configured
to reach it over the Project Server).

If DaVinciResolveScript is not available, orchestrate.py falls back to
FFmpeg-only extraction automatically — no action needed here.
"""
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path

import config
from segment_selector import Segment

log = logging.getLogger(__name__)


@dataclass
class ResolveTimeline:
    project_name: str
    render_job_id: str
    output_path: Path


def build_and_render(
    source_video: Path,
    segment: Segment,
    index: int,
    fps: float | None = None,
) -> ResolveTimeline:
    """
    Create a Resolve project/timeline for one Short segment and start rendering.
    Returns a ResolveTimeline with the render job ID to poll.
    """
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError as e:
        raise ImportError("DaVinciResolveScript not available") from e

    fps = fps or config.FPS
    project_name = _safe_name(f"Short_{index:02d}_{segment.title}", max_len=60)

    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError("Could not connect to DaVinci Resolve")

    pm = resolve.GetProjectManager()

    project = pm.CreateProject(project_name)
    if not project:
        raise RuntimeError(f"Failed to create Resolve project: {project_name}")

    # ── 9:16 vertical for Shorts ──────────────────────────────────────────────
    project.SetSetting("timelineResolutionWidth",  "1080")
    project.SetSetting("timelineResolutionHeight", "1920")
    project.SetSetting("timelineFrameRate",         _fps_string(fps))

    mp = project.GetMediaPool()

    clips = mp.ImportMedia([str(source_video)])
    if not clips:
        raise RuntimeError(f"Failed to import media: {source_video}")

    timeline = mp.CreateEmptyTimeline(segment.safe_title)
    if not timeline:
        raise RuntimeError("Failed to create empty timeline")

    project.SetCurrentTimeline(timeline)

    start_frame = math.floor(segment.start * fps)
    end_frame   = math.ceil(segment.end   * fps)

    success = mp.AppendToTimeline([{
        "mediaPoolItem": clips[0],
        "startFrame":    start_frame,
        "endFrame":      end_frame,
        "mediaType":     1,   # video + audio
    }])

    if not success:
        raise RuntimeError("AppendToTimeline failed")

    # ── Transitions (matching existing Forge Phase 2 config) ──────────────────
    _add_transitions(timeline)

    # ── Render settings ───────────────────────────────────────────────────────
    config.RESOLVE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = config.RESOLVE_OUTPUT_DIR / f"{project_name}_raw.mp4"

    project.SetRenderSettings({
        "SelectAllFrames": True,
        "TargetDir":       str(config.RESOLVE_OUTPUT_DIR),
        "CustomName":      f"{project_name}_raw",
        "FormatWidth":     1080,
        "FormatHeight":    1920,
        "VideoQuality":    0,   # Best
    })

    job_id = project.AddRenderJob()
    if not job_id:
        raise RuntimeError("AddRenderJob returned no job ID")

    project.StartRendering(job_id)
    log.info(f"Resolve render started: {project_name} [job={job_id}]")

    return ResolveTimeline(
        project_name=project_name,
        render_job_id=job_id,
        output_path=output_path,
    )


def wait_for_render(project, job_id: str, timeout: int = 900, poll: int = 5) -> bool:
    """Poll Resolve render status until complete, failed, or timeout."""
    elapsed = 0
    while elapsed < timeout:
        status = project.GetRenderJobStatus(job_id)
        state  = status.get("JobStatus", "")
        pct    = status.get("CompletionPercentage", 0)

        if state == "Complete":
            log.info(f"Resolve render complete [job={job_id}]")
            return True
        if state == "Failed":
            log.error(f"Resolve render FAILED [job={job_id}]: {status}")
            return False

        log.debug(f"Rendering… {pct:.0f}% ({elapsed}s)")
        time.sleep(poll)
        elapsed += poll

    log.error(f"Render timeout after {timeout}s [job={job_id}]")
    return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _add_transitions(timeline):
    """30-frame Cross Dissolve at clip head — matching Forge Phase 2 convention."""
    try:
        clips = timeline.GetItemListInTrack("video", 1)
        if clips:
            timeline.AddTransition("Cross Dissolve", clips[0], 0, 30, 0)
    except Exception as e:
        log.warning(f"Transition add failed (non-fatal): {e}")


def _safe_name(name: str, max_len: int = 60) -> str:
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
    return safe[:max_len]


def _fps_string(fps: float) -> str:
    # Resolve expects "23.976", "29.97", "30", "59.94", etc.
    mapping = {
        23.976: "23.976",
        24.0:   "24",
        25.0:   "25",
        29.97:  "29.97",
        30.0:   "30",
        59.94:  "59.94",
        60.0:   "60",
    }
    return mapping.get(round(fps, 3), str(fps))
