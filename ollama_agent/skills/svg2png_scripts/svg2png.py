#!/usr/bin/env python3
"""Convert SVG files to high-resolution PNG.

Supports multiple backends with automatic fallback:
  1. cairosvg  (best quality, requires Cairo native library)
  2. svglib+Pillow  (pure Python, no native deps — uses svglib to parse,
     renders via Pillow without reportlab's renderPM)
  3. inkscape CLI  (if Inkscape is installed)

Usage:
    python svg2png.py input.svg                    # -> input.png (2x scale)
    python svg2png.py input.svg -o output.png      # custom output path
    python svg2png.py input.svg -s 4               # 4x scale for high-res
    python svg2png.py input.svg -w 2048            # specific width
    python svg2png.py input.svg -d 300             # 300 DPI
    python svg2png.py *.svg                        # batch convert
    python svg2png.py folder/                      # convert all SVGs in folder
    python svg2png.py input.svg -b svglib          # force backend
    python svg2png.py --list-backends               # show available backends
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# Backend detection — actually test that the import works, not just exists
# ---------------------------------------------------------------------------

def _test_cairosvg():
    """Test if cairosvg can actually be imported and used."""
    try:
        import cairosvg
        # Quick smoke test — try to call svg2png with empty input to verify
        # the native Cairo lib is actually loadable
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = f.name
        try:
            # Minimal valid SVG
            cairosvg.svg2png(bytestring=b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>',
                             write_to=tmp)
            os.unlink(tmp)
            return True
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            return False
    except (ImportError, OSError):
        return False


def _test_svglib():
    """Test if svglib + pypdfium2 can be imported (no Cairo needed)."""
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF
        import pypdfium2
        return True
    except ImportError:
        return False


def _test_playwright():
    """Test if Playwright is available."""
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        return False


def _test_inkscape():
    """Test if Inkscape CLI is available."""
    return shutil.which("inkscape") is not None


def detect_backends():
    """Return dict of {name: available_bool} for each backend."""
    return {
        "cairosvg": _test_cairosvg(),
        "playwright": _test_playwright(),
        "svglib": _test_svglib(),
        "inkscape": _test_inkscape(),
    }


def get_best_backend(preferred=None):
    """Return the best available backend name, or None if none work."""
    available = detect_backends()

    if preferred:
        if available.get(preferred):
            return preferred
        print(f"Warning: Backend '{preferred}' is not available.")
        print(f"Available backends: {[k for k, v in available.items() if v]}")
        return None

    # Priority: cairosvg (best) > playwright (excellent) > svglib (fallback) > inkscape
    for name in ("cairosvg", "playwright", "svglib", "inkscape"):
        if available.get(name):
            return name
    return None


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def convert_cairosvg(input_path, output_path, scale=2, width=None, height=None, dpi=None):
    """Convert using cairosvg (best quality, needs Cairo native lib)."""
    import cairosvg

    kwargs = {}
    if width is not None:
        kwargs["output_width"] = width
    if height is not None:
        kwargs["output_height"] = height
    if dpi is not None:
        kwargs["dpi"] = dpi
    if not width and not height and not dpi:
        kwargs["scale"] = scale

    cairosvg.svg2png(url=input_path, write_to=output_path, **kwargs)


def _sanitize_svg(svg_bytes):
    """Fix common SVG issues that trip up svglib.

    svglib's CSS parser (cssselect2/tinycss2) chokes on:
    - Pseudo-classes like :round, :hover, :focus
    - @keyframes animation blocks
    - stroke-dasharray:0 (zero-length dash cycles)

    Strategy: Remove the <style> block entirely (inline style= attributes
    still work fine), and fix dash-array issues in the remaining markup.
    """
    import re

    text = svg_bytes.decode("utf-8", errors="replace")

    # Remove entire <style>...</style> blocks — svglib can't handle CSS
    # selectors with pseudo-classes, @keyframes, etc. Inline style=
    # attributes are unaffected and still work fine.
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)

    # Fix stroke-dasharray:0 in inline styles/attributes
    text = re.sub(r'stroke-dasharray\s*:\s*0(?:px)?\s*;?', 'stroke-dasharray:none;', text)
    text = re.sub(r'stroke-dasharray\s*=\s*"0(?:px)?"', 'stroke-dasharray="none"', text)

    return text.encode("utf-8")


def convert_svglib(input_path, output_path, scale=2, width=None, height=None, dpi=None):
    """Convert using svglib + reportlab PDF + pypdfium2 (pure Python, no Cairo).

    Pipeline: SVG -> sanitize -> svglib -> reportlab PDF -> pypdfium2 -> PNG
    This avoids renderPM which requires the Cairo native library.
    """
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF
    from reportlab.lib.pagesizes import A4
    import pypdfium2
    from PIL import Image
    import io
    import tempfile

    # Read and sanitize SVG to fix common issues
    with open(input_path, "rb") as f:
        svg_data = f.read()
    svg_data = _sanitize_svg(svg_data)

    drawing = svg2rlg(io.BytesIO(svg_data))
    if drawing is None:
        raise ValueError(f"svglib could not parse {input_path}")

    orig_w, orig_h = drawing.width, drawing.height
    if orig_w <= 0 or orig_h <= 0:
        raise ValueError(f"SVG has invalid dimensions: {orig_w}x{orig_h}")

    # Determine output pixel dimensions
    if width and height:
        out_w, out_h = width, height
    elif width:
        ratio = width / orig_w
        out_w, out_h = width, orig_h * ratio
    elif height:
        ratio = height / orig_h
        out_w, out_h = orig_w * ratio, height
    elif dpi:
        factor = dpi / 72.0
        out_w, out_h = orig_w * factor, orig_h * factor
    else:
        out_w, out_h = orig_w * scale, orig_h * scale

    out_w, out_h = int(out_w), int(out_h)

    # Step 1: SVG -> reportlab Drawing -> PDF (no Cairo needed)
    pdf_buf = io.BytesIO()
    renderPDF.drawToFile(drawing, pdf_buf)
    pdf_bytes = pdf_buf.getvalue()

    # Step 2: PDF -> PNG via pypdfium2 (pure Python PDF renderer)
    pdf = pypdfium2.PdfDocument(pdf_bytes)
    page = pdf[0]
    # Render at scale that gives us at least the target size
    render_scale = max(out_w / (orig_w if orig_w else 1), out_h / (orig_h if orig_h else 1), scale)
    bitmap = page.render(scale=render_scale)
    pil_img = bitmap.to_pil()

    # Resize to exact target dimensions
    if pil_img.size != (out_w, out_h):
        pil_img = pil_img.resize((out_w, out_h), Image.LANCZOS)

    pil_img.save(output_path, "PNG", dpi=(dpi or int(72 * scale), dpi or int(72 * scale)))
    pdf.close()


def convert_playwright(input_path, output_path, scale=2, width=None, height=None, dpi=None):
    """Convert using Playwright (browser-based, highest fidelity).

    Renders the SVG in a headless Chromium browser, which uses the same
    SVG engine as Chrome/Firefox — producing pixel-perfect output that
    matches what you'd see in a browser. Handles CSS, animations, filters,
    gradients, and all SVG features perfectly.
    """
    from playwright.sync_api import sync_playwright
    import base64
    import os

    # Read SVG to determine intrinsic dimensions
    with open(input_path, "rb") as f:
        svg_data = f.read()
    svg_text = svg_data.decode("utf-8", errors="replace")

    # Parse viewBox/width/height from the ROOT <svg> element only.
    # Extract the opening <svg ...> tag to avoid matching attributes on
    # child elements. Skip percentage values (e.g. width="100%").
    import re
    root_match = re.search(r'<svg[^>]*>', svg_text)
    root_tag = root_match.group(0) if root_match else svg_text[:500]

    w_match = re.search(r'\bwidth\s*=\s*["\'](\d+(?:\.\d+)?)(?:px)?["\']', root_tag)
    h_match = re.search(r'\bheight\s*=\s*["\'](\d+(?:\.\d+)?)(?:px)?["\']', root_tag)
    vb_match = re.search(r'viewBox\s*=\s*["\']\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)', root_tag)

    if w_match:
        svg_w = float(w_match.group(1))
    elif vb_match:
        svg_w = float(vb_match.group(3))
    else:
        svg_w = 800

    if h_match:
        svg_h = float(h_match.group(1))
    elif vb_match:
        svg_h = float(vb_match.group(4))
    else:
        svg_h = 600

    # Determine the CSS layout size (the on-screen size in CSS pixels).
    # The final PNG pixel dimensions = layout size × device_scale_factor.
    if width and height:
        layout_w, layout_h = width, height
        dsf = min(max(scale, 1.0), 4.0)
    elif width:
        ratio = width / svg_w
        layout_w, layout_h = width, svg_h * ratio
        dsf = min(max(scale, 1.0), 4.0)
    elif height:
        ratio = height / svg_h
        layout_w, layout_h = svg_w * ratio, height
        dsf = min(max(scale, 1.0), 4.0)
    elif dpi:
        # DPI mode: layout = intrinsic size, dsf = dpi/96
        layout_w, layout_h = svg_w, svg_h
        dsf = min(max(dpi / 96.0, 1.0), 4.0)
    else:
        # Scale mode: layout = intrinsic size, dsf = scale
        layout_w, layout_h = svg_w, svg_h
        dsf = min(max(scale, 1.0), 4.0)

    layout_w, layout_h = int(layout_w), int(layout_h)

    # Strip width/height/max-width from the root <svg> so it fills the
    # container exactly, then inline it directly in the HTML body.
    import re as _re
    svg_inline = svg_text
    # Remove width, height, and max-width from the root <svg> tag
    svg_inline = _re.sub(r'(<svg[^>]*?)\swidth\s*=\s*["\'][^"\']*["\']', r'\1', svg_inline, count=1)
    svg_inline = _re.sub(r'(<svg[^>]*?)\sheight\s*=\s*["\'][^"\']*["\']', r'\1', svg_inline, count=1)
    svg_inline = _re.sub(r'(<svg[^>]*?)\sstyle\s*=\s*["\'][^"\']*["\']', r'\1', svg_inline, count=1)
    # Add width/height to fill the container
    svg_inline = svg_inline.replace('<svg', f'<svg width="{layout_w}" height="{layout_h}"', 1)

    html = f"""<!DOCTYPE html>
<html><head><style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: {layout_w}px; height: {layout_h}px; overflow: hidden; }}
  svg {{ display: block; }}
</style></head>
<body>{svg_inline}</body></html>"""

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": layout_w, "height": layout_h},
                                device_scale_factor=dsf)
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=output_path, full_page=False, omit_background=False)
        browser.close()


def convert_inkscape(input_path, output_path, scale=2, width=None, height=None, dpi=None):
    """Convert using Inkscape CLI."""
    cmd = ["inkscape", input_path, "--export-type=png", "--export-filename", output_path]

    if width:
        cmd.extend(["--export-width", str(width)])
    elif height:
        cmd.extend(["--export-height", str(height)])
    elif dpi:
        cmd.extend(["--export-dpi", str(dpi)])
    else:
        cmd.extend(["--export-dpi", str(int(96 * scale))])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Inkscape failed: {result.stderr}")


BACKEND_FUNCS = {
    "cairosvg": convert_cairosvg,
    "playwright": convert_playwright,
    "svglib": convert_svglib,
    "inkscape": convert_inkscape,
}


# ---------------------------------------------------------------------------
# Core conversion
# ---------------------------------------------------------------------------

def svg_to_png(input_path, output_path=None, scale=2, width=None, height=None,
               dpi=None, backend=None):
    """Convert a single SVG file to PNG.

    Returns:
        (output_path, backend_name) on success, (None, None) on failure.
    """
    if not os.path.isfile(input_path):
        print(f"Error: Input file not found: {input_path}")
        return None, None

    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + ".png"

    be = get_best_backend(preferred=backend)
    if be is None:
        print("Error: No SVG conversion backend available. Install one of:")
        print("  pip install cairosvg          (best quality, needs Cairo native lib)")
        print("  pip install svglib Pillow     (pure Python, no native deps)")
        print("  Or install Inkscape and add to PATH")
        return None, None

    convert_fn = BACKEND_FUNCS[be]
    try:
        convert_fn(input_path, output_path, scale=scale, width=width,
                    height=height, dpi=dpi)
        size_kb = os.path.getsize(output_path) / 1024
        print(f"  \u2713 {input_path} -> {output_path} ({size_kb:.1f} KB) [{be}]")
        return output_path, be
    except Exception as e:
        print(f"  \u2717 {input_path}: {e}")
        return None, None


def collect_svg_paths(paths):
    """Expand paths into a list of SVG files."""
    svg_files = []
    for path in paths:
        if os.path.isfile(path):
            svg_files.append(path)
        elif os.path.isdir(path):
            found = glob.glob(os.path.join(path, "**", "*.svg"), recursive=True)
            svg_files.extend(sorted(found))
        else:
            found = glob.glob(path, recursive=True)
            if found:
                svg_files.extend(sorted(found))
            else:
                print(f"Warning: No SVG files found for: {path}")
    return svg_files


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert SVG files to high-resolution PNG.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s logo.svg                  Convert at 2x scale
  %(prog)s logo.svg -s 4             Convert at 4x scale (ultra high-res)
  %(prog)s logo.svg -w 2048          Set output width to 2048px
  %(prog)s logo.svg -d 300           Set DPI to 300
  %(prog)s *.svg                     Batch convert all SVGs
  %(prog)s assets/                   Convert all SVGs in folder
  %(prog)s logo.svg -o hi-res.png    Custom output filename
  %(prog)s logo.svg -b svglib        Force svglib backend
  %(prog)s --list-backends           Show available backends

Backends (auto-detected in priority order):
  cairosvg   Best quality, requires Cairo native library
  svglib     Pure Python (svglib+Pillow), no native deps
  inkscape   Uses Inkscape CLI if installed
""",
    )
    parser.add_argument("inputs", nargs="*", help="SVG files, directories, or glob patterns")
    parser.add_argument("-o", "--output", help="Output PNG path (single file only)")
    parser.add_argument("-s", "--scale", type=float, default=2, help="Scale factor (default: 2)")
    parser.add_argument("-w", "--width", type=int, help="Output width in pixels")
    parser.add_argument("--height", type=int, help="Output height in pixels")
    parser.add_argument("-d", "--dpi", type=int, help="DPI for output")
    parser.add_argument("-b", "--backend", choices=["cairosvg", "playwright", "svglib", "inkscape"],
                        help="Force a specific backend")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress output except errors")
    parser.add_argument("--list-backends", action="store_true", help="Show available backends and exit")

    args = parser.parse_args()

    # List backends mode — no input files needed
    if args.list_backends:
        available = detect_backends()
        print("Backend availability:")
        for name, ok in available.items():
            status = "\u2713 available" if ok else "\u2717 not available"
            print(f"  {name}: {status}")
        best = get_best_backend()
        print(f"\nBest available: {best or 'NONE'}")
        if not best:
            print("\nInstall one of:")
            print("  pip install cairosvg          (best quality, needs Cairo native lib)")
            print("  pip install svglib Pillow     (pure Python, no native deps)")
            print("  Or install Inkscape and add to PATH")
        return

    if not args.inputs:
        parser.error("the following arguments are required: inputs (use --list-backends to check backends)")

    svg_files = collect_svg_paths(args.inputs)
    if not svg_files:
        print("Error: No SVG files found.")
        sys.exit(1)

    if args.output and len(svg_files) > 1:
        print("Error: --output can only be used with a single input file.")
        sys.exit(1)

    success = 0
    for svg_path in svg_files:
        out_path = args.output if args.output else None
        result, _ = svg_to_png(
            svg_path,
            output_path=out_path,
            scale=args.scale,
            width=args.width,
            height=args.height,
            dpi=args.dpi,
            backend=args.backend,
        )
        if result:
            success += 1

    total = len(svg_files)
    if not args.quiet and total > 1:
        print(f"\nConverted {success}/{total} files.")

    sys.exit(0 if success == total else 1)


if __name__ == "__main__":
    main()
