#!/usr/bin/env python3
"""Add a running MM:SS timestamp overlay to a video file.

Generates an ASS subtitle file with per-second timestamps and uses FFmpeg's
subtitles filter to burn them into the video. This avoids the drawtext filter's
notorious escaping issues on Windows.

Usage:
    python add_timestamp.py <input_video_path>

Output:
    <input_name>-timestamped.mp4 in the same directory as the input.

Requirements:
    - FFmpeg (with libass support) on PATH
    - ffprobe on PATH
"""

import subprocess
import sys
import os
import math

# Fix Windows UTF-8 output for non-English locales
sys.stdout.reconfigure(encoding='utf-8')


def get_video_info(input_video):
    """Get duration and resolution of the input video using ffprobe."""
    # Duration
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", input_video],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"❌ ffprobe failed to get duration:\n{result.stderr}")
        sys.exit(1)
    duration = float(result.stdout.strip())

    # Resolution
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=s=x:p=0", input_video],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"❌ ffprobe failed to get resolution:\n{result.stderr}")
        sys.exit(1)
    width, height = map(int, result.stdout.strip().split('x'))

    return duration, width, height


def generate_ass_file(duration, width, height, ass_path,
                      fontname="Consolas", fontsize=36,
                      alignment=9, margin_h=10, margin_v=10):
    """Generate an ASS subtitle file with per-second MM:SS timestamps.

    Args:
        duration: Video duration in seconds.
        width: Video width in pixels.
        height: Video height in pixels.
        ass_path: Output path for the ASS file.
        fontname: Font name (default: Consolas, monospace).
        fontsize: Font size in pixels (default: 36).
        alignment: ASS alignment value (9=top-right, 7=top-left,
                   3=bottom-right, 1=bottom-left).
        margin_h: Horizontal margin in pixels.
        margin_v: Vertical margin in pixels.
    """
    total_seconds = int(math.ceil(duration))

    # ASS colors: &HAABBGGRR (AA alpha: 00=opaque, FF=transparent)
    # PrimaryColour: white (&H00FFFFFF)
    # BackColour: semi-transparent black (&H80000000 = 50% opacity)
    ass_content = f"""[Script Info]
Title: Timestamp
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Timestamp,{fontname},{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,3,2,0,{alignment},{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    for sec in range(total_seconds + 1):
        mins = sec // 60
        secs = sec % 60
        start_h = sec // 3600
        start_m = (sec % 3600) // 60
        start_s = sec % 60
        end_sec = min(sec + 1, duration)
        end_h = int(end_sec) // 3600
        end_m = (int(end_sec) % 3600) // 60
        end_s = int(end_sec) % 60
        end_cs = int(round((end_sec - int(end_sec)) * 100))

        start_time = f"{start_h}:{start_m:02d}:{start_s:02d}.00"
        end_time = f"{end_h}:{end_m:02d}:{end_s:02d}.{end_cs:02d}"
        text = f"{mins:02d}:{secs:02d}"

        ass_content += f"Dialogue: 0,{start_time},{end_time},Timestamp,,0,0,0,,{text}\n"

    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

    return total_seconds + 1


def run_ffmpeg(input_video, output_video, ass_path, preset="fast", crf=18):
    """Run FFmpeg to burn the ASS subtitles into the video."""
    # Use a simple relative filename to avoid Windows path escaping issues
    # with FFmpeg's subtitles filter (colons in C: drive letters break parsing)
    ass_basename = os.path.basename(ass_path)
    work_dir = os.path.dirname(ass_path)

    cmd = [
        "ffmpeg",
        "-i", input_video,
        "-vf", f"subtitles={ass_basename}",
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-y",
        output_video
    ]

    print(f"\nRunning FFmpeg...")
    print(f"  Input:    {input_video}")
    print(f"  Output:   {output_video}")
    print(f"  Subtitles: {ass_path}")
    print(f"  Preset:   {preset}, CRF: {crf}")

    result = subprocess.run(cmd, capture_output=True, text=True,
                           cwd=work_dir, timeout=600)

    if result.returncode == 0:
        size_mb = os.path.getsize(output_video) / (1024 * 1024)
        print(f"\n✅ Done! Output saved to:\n   {output_video}")
        print(f"   File size: {size_mb:.1f} MB")
        return True
    else:
        print(f"\n❌ FFmpeg failed (exit code {result.returncode})")
        print(f"STDERR:\n{result.stderr[-3000:]}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python add_timestamp.py <input_video_path>")
        print("       python add_timestamp.py <input_video_path> --preset ultrafast")
        print("       python add_timestamp.py <input_video_path> --crf 22")
        sys.exit(1)

    input_video = os.path.abspath(sys.argv[1])

    if not os.path.isfile(input_video):
        print(f"❌ File not found: {input_video}")
        sys.exit(1)

    # Parse optional args
    preset = "fast"
    crf = 18
    for arg in sys.argv[2:]:
        if arg.startswith("--preset="):
            preset = arg.split("=", 1)[1]
        elif arg == "--preset" and sys.argv.index(arg) + 1 < len(sys.argv):
            preset = sys.argv[sys.argv.index(arg) + 1]
        elif arg.startswith("--crf="):
            crf = int(arg.split("=", 1)[1])
        elif arg == "--crf" and sys.argv.index(arg) + 1 < len(sys.argv):
            crf = int(sys.argv[sys.argv.index(arg) + 1])

    # Derive output path
    base, ext = os.path.splitext(input_video)
    output_video = f"{base}-timestamped{ext}"
    ass_path = os.path.join(os.path.dirname(input_video), "timestamps.ass")

    # Get video info
    print(f"Analyzing: {input_video}")
    duration, width, height = get_video_info(input_video)
    print(f"  Resolution: {width}x{height}")
    print(f"  Duration:    {duration:.2f}s ({int(duration // 60)}m {int(duration % 60)}s)")

    # Generate ASS subtitle file
    entry_count = generate_ass_file(duration, width, height, ass_path)
    print(f"  Generated {entry_count} subtitle entries → {ass_path}")

    # Run FFmpeg
    success = run_ffmpeg(input_video, output_video, ass_path, preset=preset, crf=crf)

    # Clean up ASS file
    try:
        os.remove(ass_path)
        print(f"  Cleaned up: {ass_path}")
    except OSError:
        pass

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
