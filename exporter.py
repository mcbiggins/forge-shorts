"""
Forge Shorts — FFmpeg Exporter
Handles two responsibilities:

1. Segment extraction (fallback when Resolve is unavailable)
   - Cuts the short from source with 9:16 padding via scale+pad filter

2. Post-render processing (always runs)
   - Two-pass loudnorm to YouTube Shorts spec (-14 LUFS)
   - ASS subtitle burn-in (CapCut-style word highlight)
   - Final H.264/AAC encode optimized for mobile
"""
import json
import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


# ── Segment extraction (Resolve fallback) ─────────────────────────────────────

def ffmpeg_extract(
    source: Path,
    start: float,
    end: float,
    output: Path,
    crop_x: float = 0.5,
    crop_y: float = 0.5,
) -> Path:
    """
    Cut a segment from source video and crop to 1080x1920 (9:16).
    crop_x/crop_y control where the crop window is positioned:
      0.0 = left/top, 0.5 = center, 1.0 = right/bottom
    """
    duration = end - start
    output.parent.mkdir(parents=True, exist_ok=True)

    # Smart crop: extract a 9:16 slice from the source frame.
    # First scale so the shorter dimension fits, then crop to 1080x1920.
    #
    # For 16:9 source (1920x1080):
    #   - Scale height to 1920 → width becomes 3413
    #   - Crop 1080 wide from position based on crop_x
    #
    # crop_x maps to x offset: 0.0=left edge, 0.5=center, 1.0=right edge
    vf = (
        f"scale=-1:1920:force_original_aspect_ratio=increase,"
        f"scale=max(1080\\,iw):max(1920\\,ih),"
        f"crop=1080:1920:"
        f"(iw-1080)*{crop_x:.2f}:(ih-1920)*{crop_y:.2f}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss",  str(start),
        "-i",   str(source),
        "-t",   str(duration),
        "-vf",  vf,
        "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "18", "-b:v", "0",
        "-c:a", "aac", "-b:a", "192k",
        str(output),
    ]

    log.info(f"FFmpeg extract → {output.name} ({duration:.1f}s, crop=({crop_x:.2f}, {crop_y:.2f}))")
    _run(cmd, label="extract")
    return output


# ── Audio normalization ───────────────────────────────────────────────────────

def normalize_audio(input_path: Path, output_path: Path) -> Path:
    """
    Two-pass EBU R128 loudnorm to -14 LUFS (YouTube Shorts spec).
    Returns output_path on success, input_path if normalization fails.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Pass 1: measure
    pass1 = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(input_path),
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )

    # loudnorm stats come out on stderr
    match = re.search(r"\{[^{}]+\}", pass1.stderr, re.DOTALL)
    if not match:
        log.warning("Could not parse loudnorm stats — skipping normalization")
        return input_path

    try:
        stats = json.loads(match.group())
    except json.JSONDecodeError:
        log.warning("Invalid loudnorm JSON — skipping normalization")
        return input_path

    # Pass 2: apply
    af = (
        f"loudnorm=I=-14:TP=-1.5:LRA=11"
        f":measured_I={stats['input_i']}"
        f":measured_TP={stats['input_tp']}"
        f":measured_LRA={stats['input_lra']}"
        f":measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}"
        f":linear=true:print_format=summary"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i",   str(input_path),
        "-af",  af,
        "-c:v", "copy",          # don't re-encode video in normalization pass
        str(output_path),
    ]

    try:
        _run(cmd, label="loudnorm")
        log.info(f"Audio normalized → {output_path.name}")
        return output_path
    except RuntimeError as e:
        log.warning(f"Loudnorm pass 2 failed ({e}) — using un-normalized audio")
        return input_path


# ── Subtitle burn-in ──────────────────────────────────────────────────────────

def burn_subtitles(
    raw_video: Path,
    ass_file: Path,
    output_path: Path,
) -> Path:
    """
    Burn ASS karaoke subtitles into the video via FFmpeg's `ass` filter.
    Final encode: H.264 slow/CRF18, AAC 192k, faststart for mobile.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # FFmpeg ass filter needs escaped path (colons and backslashes)
    ass_str = str(ass_file).replace("\\", "/")
    # On Linux this is usually fine; escape colon just in case
    ass_str = ass_str.replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i",      str(raw_video),
        "-vf",     f"ass={ass_str}",
        "-c:v",    "h264_nvenc",
        "-preset", "p4",
        "-rc",     "vbr",
        "-cq",     "18",
        "-b:v",    "0",
        "-c:a",    "aac",
        "-b:a",    "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    log.info(f"Burning subtitles → {output_path.name}")
    _run(cmd, label="subtitle burn")
    return output_path


# ── Montage: extract + concat multiple clips ─────────────────────────────────

def ffmpeg_extract_montage(
    source: Path,
    clips: list,
    output: Path,
    crop_x: float = 0.5,
    crop_y: float = 0.5,
    transition: str = "fadeblack",
    transition_dur: float = 0.5,
) -> Path:
    """
    Extract multiple clips from source, crop each to 9:16, apply dissolve
    transitions between clips, and output one file.

    transition: FFmpeg xfade transition name (fadeblack, dissolve, etc.)
    transition_dur: seconds of overlap per transition
    """
    output.parent.mkdir(parents=True, exist_ok=True)

    vf_crop = (
        f"scale=-1:1920:force_original_aspect_ratio=increase,"
        f"scale=max(1080\\,iw):max(1920\\,ih),"
        f"crop=1080:1920:"
        f"(iw-1080)*{crop_x:.2f}:(ih-1920)*{crop_y:.2f}"
    )

    clip_files = []
    try:
        # Extract each clip
        for i, clip in enumerate(clips):
            tmp = output.parent / f"_montage_clip_{i:02d}.mp4"
            clip_files.append(tmp)
            dur = clip.end - clip.start
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(clip.start),
                "-i", str(source),
                "-t", str(dur),
                "-vf", vf_crop,
                "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "18", "-b:v", "0",
                "-c:a", "aac", "-b:a", "192k",
                str(tmp),
            ]
            log.info(f"  Montage clip {i+1}/{len(clips)}: {clip.start:.1f}s-{clip.end:.1f}s ({dur:.1f}s)")
            _run(cmd, label=f"montage clip {i+1}")

        if len(clip_files) == 1:
            # Single clip, just rename
            clip_files[0].rename(output)
            clip_files = []
            return output

        # Build xfade filter chain for dissolve transitions between clips
        # xfade needs decoded input, so we re-encode during the merge step
        inputs = []
        for cf in clip_files:
            inputs.extend(["-i", str(cf)])

        # Build the video xfade filter chain
        # For N clips: N-1 xfade filters chained together
        clip_durations = [(clips[i].end - clips[i].start) for i in range(len(clips))]
        vf_parts = []
        af_parts = []
        offset = clip_durations[0] - transition_dur

        if len(clip_files) == 2:
            vf_parts.append(
                f"[0:v][1:v]xfade=transition={transition}:duration={transition_dur}:offset={offset:.3f}[vout]"
            )
            af_parts.append(
                f"[0:a][1:a]acrossfade=d={transition_dur}[aout]"
            )
        else:
            # Chain: [0][1]->xfade->[v1], [v1][2]->xfade->[v2], etc.
            prev = "0:v"
            prev_a = "0:a"
            for i in range(1, len(clip_files)):
                out_label = "vout" if i == len(clip_files) - 1 else f"v{i}"
                out_label_a = "aout" if i == len(clip_files) - 1 else f"a{i}"
                vf_parts.append(
                    f"[{prev}][{i}:v]xfade=transition={transition}"
                    f":duration={transition_dur}:offset={offset:.3f}[{out_label}]"
                )
                af_parts.append(
                    f"[{prev_a}][{i}:a]acrossfade=d={transition_dur}[{out_label_a}]"
                )
                prev = out_label
                prev_a = out_label_a
                # Next offset: accumulated duration minus overlaps so far
                offset += clip_durations[i] - transition_dur

        filter_complex = ";".join(vf_parts + af_parts)

        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "18", "-b:v", "0",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output),
        ]

        log.info(f"Montage merge with {transition} transitions -> {output.name} ({len(clips)} clips)")
        _run(cmd, label="montage xfade")

    finally:
        for cf in clip_files:
            try:
                cf.unlink(missing_ok=True)
            except Exception:
                pass

    return output


# ── Internal helper ───────────────────────────────────────────────────────────

def _run(cmd: list, label: str = "ffmpeg"):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"FFmpeg [{label}] stderr:\n{result.stderr[-2000:]}")
        raise RuntimeError(f"FFmpeg {label} failed (exit {result.returncode})")
