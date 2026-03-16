"""
Forge Shorts — Content Presets
Each preset auto-configures framing, clip style, durations, and AI behavior.
Users can tune individual settings after selecting a preset.
"""

# Framing modes
FRAMING_CENTER_CROP = "center_crop"      # Static center slice from 16:9
FRAMING_SMART_FRAME = "smart_frame"      # Claude Vision picks crop position
FRAMING_FACE_TRACK = "face_track"        # Face detection + smooth pan
FRAMING_SPLIT_LAYOUT = "split_layout"    # Wide shot top + zoomed bottom

# Clip styles
CLIP_SEQUENTIAL = "sequential"           # Single continuous cut
CLIP_MONTAGE = "montage"                 # Best moments stitched together

PRESETS = {
    "gaming": {
        "label": "Gaming",
        "description": "Gameplay highlights, facecam + overlay aware",
        "icon": "🎮",
        "framing": FRAMING_SPLIT_LAYOUT,
        "clipStyle": CLIP_SEQUENTIAL,
        "visionFrames": 2,
        "minDur": 30,
        "targetDur": 45,
        "maxDur": 60,
        "segCount": 4,
        "wordsPerGroup": 3,
        "costLevel": 2,  # 1-5 scale
    },
    "automotive": {
        "label": "Automotive",
        "description": "Builds, drives, reveals — dynamic framing",
        "icon": "🏎",
        "framing": FRAMING_SMART_FRAME,
        "clipStyle": CLIP_MONTAGE,
        "visionFrames": 4,
        "minDur": 30,
        "targetDur": 50,
        "maxDur": 60,
        "segCount": 3,
        "wordsPerGroup": 4,
        "costLevel": 3,
    },
    "interview": {
        "label": "Interview",
        "description": "Talking heads, speaker tracking, clean cuts",
        "icon": "🎙",
        "framing": FRAMING_FACE_TRACK,
        "clipStyle": CLIP_SEQUENTIAL,
        "visionFrames": 3,
        "minDur": 30,
        "targetDur": 45,
        "maxDur": 60,
        "segCount": 5,
        "wordsPerGroup": 4,
        "costLevel": 3,
    },
    "vlogging": {
        "label": "Vlogging",
        "description": "Mixed scenes, smart framing follows the action",
        "icon": "📱",
        "framing": FRAMING_SMART_FRAME,
        "clipStyle": CLIP_MONTAGE,
        "visionFrames": 4,
        "minDur": 25,
        "targetDur": 40,
        "maxDur": 55,
        "segCount": 4,
        "wordsPerGroup": 4,
        "costLevel": 3,
    },
    "howto": {
        "label": "How-To",
        "description": "Tutorials, demos — keep it centered and clear",
        "icon": "🔧",
        "framing": FRAMING_CENTER_CROP,
        "clipStyle": CLIP_SEQUENTIAL,
        "visionFrames": 0,
        "minDur": 30,
        "targetDur": 50,
        "maxDur": 60,
        "segCount": 3,
        "wordsPerGroup": 4,
        "costLevel": 1,
    },
}

# Default preset
DEFAULT_PRESET = "gaming"

# Framing mode metadata for UI
FRAMING_MODES = {
    FRAMING_CENTER_CROP: {
        "label": "Center Crop",
        "description": "Static center slice, no AI analysis",
        "costAdd": 0,
    },
    FRAMING_SMART_FRAME: {
        "label": "Smart Frame",
        "description": "Claude Vision picks the best crop per segment",
        "costAdd": 1,
    },
    FRAMING_FACE_TRACK: {
        "label": "Face Track",
        "description": "Detects and follows speakers",
        "costAdd": 2,
    },
    FRAMING_SPLIT_LAYOUT: {
        "label": "Split Layout",
        "description": "Wide shot + zoomed speaker panel",
        "costAdd": 1,
    },
}

CLIP_STYLES = {
    CLIP_SEQUENTIAL: {
        "label": "Sequential",
        "description": "Single continuous clip from the video",
        "costAdd": 0,
    },
    CLIP_MONTAGE: {
        "label": "Montage",
        "description": "Best moments stitched together",
        "costAdd": 1,
    },
}
