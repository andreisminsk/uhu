---
name: video-timestamp
triggers:
  - add timestamp to video
  - timestamp video
  - time marker on video
  - video timestamp
  - add timer to video
  - burn time into video
  - overlay time on video
description: Add a running MM:SS timestamp overlay in the top-right corner of a video file.
---

# Video Timestamp

Add a running time marker (MM:SS) overlay to a video file, positioned in the top-right corner with 10px padding. Uses FFmpeg with an ASS subtitle burn-in approach to avoid the drawtext filter's escaping issues on Windows.

## Scripts

- `scripts/add_timestamp.py` — Generates an ASS subtitle file with per-second timestamps and runs FFmpeg to burn it into the video.

> All script paths are relative to this SKILL.md's directory.
> At runtime, they are automatically resolved to workdir-relative paths.

## Activation

Triggered when user asks to add a timestamp, timer, or time marker overlay to a video.

## Workflow

1. Ask the user for the input video file path (if not provided).
2. Run the script: `python scripts/add_timestamp.py <input_video_path>`
   - The script accepts one argument: the path to the input video.
   - It auto-detects duration and resolution using ffprobe.
   - It generates an ASS subtitle file with per-second MM:SS entries.
   - It produces an output file: `<input_name>-timestamped.mp4` in the same directory.
3. Report the output file path and size to the user.

## Customization

The user may request changes to:
- **Position**: top-right (default), top-left, bottom-right, bottom-left — adjust the ASS `Alignment` value (9=top-right, 7=top-left, 3=bottom-right, 1=bottom-left) and margins.
- **Font size**: default is 36 — adjust `Fontsize` in the ASS style.
- **Font**: default is Consolas (monospace) — change `Fontname` in the ASS style.
- **Format**: default is MM:SS — can be changed to HH:MM:SS by modifying the timestamp generation logic.
- **Background opacity**: default is 50% (black@0.5) — adjust `BackColour` alpha (&H80=50%, &H00=opaque, &HFF=transparent).

## Requirements

- **FFmpeg** must be installed and on PATH (with libass support for subtitle rendering).
- **ffprobe** must be available (usually bundled with FFmpeg).
- **Python 3** for the helper script.

## Pitfalls

- **FFmpeg drawtext escaping on Windows**: The drawtext filter requires complex escaping of colons and backslashes on Windows. This skill uses the ASS subtitle approach instead, which is much more reliable.
- **Long videos**: A 17-minute video takes ~90 seconds to encode. For very long videos, consider using `-preset ultrafast` for speed (at the cost of file size).
- **Font availability**: Consolas is used by default (monospace, avoids timer jitter). If not available, the script falls back to whatever libass finds.
- **Windows encoding**: The script includes `sys.stdout.reconfigure(encoding='utf-8')` to avoid UnicodeEncodeError on non-English Windows locales.
