#!/usr/bin/env python3
"""
Hyva Theme Upgrade - Automated Visual Diff & PerfectPixel Tool
Compares storefront pages between a baseline (staging) and target (local dev) site.
Generates side-by-side comparison, diff heatmap, and an interactive HTML report.

URLs are read from .hyva-upgrade.json (baselineUrl / targetUrl) or via --baseline / --target flags.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hyva_common as hc  # noqa: E402

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont  # noqa: F401
except ImportError:
    sys.stderr.write(
        "❌ Pillow is required for visual-diff.\n"
        "   pip install -r .agents/skills/hyva-theme-upgrade/requirements.txt\n"
        "   (on managed Python: python3 -m venv .venv && . .venv/bin/activate first)\n"
    )
    sys.exit(2)

SKILL_ROOT = Path(__file__).resolve().parent.parent

VIEWPORT_PRESETS = {
    "desktop": (1440, 900),
    "tablet": (768, 1024),
    "mobile": (375, 812),
}

def find_chrome():
    """$CHROME_BIN, then well-known Linux/macOS/Windows locations, then PATH."""
    env_bin = os.environ.get("CHROME_BIN")
    if env_bin and os.path.exists(env_bin):
        return env_bin
    candidates = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if os.path.exists(c) and os.access(c, os.X_OK):
            return c
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("No Chrome/Chromium found. Install one or set CHROME_BIN=/path/to/chrome.")

def capture_screenshot(chrome_bin, url, output_path, width, height, wait_ms=4000):
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        chrome_bin,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--ignore-certificate-errors",
        f"--window-size={width},{height}",
        f"--virtual-time-budget={wait_ms}",
        f"--screenshot={output_path}",
        url,
    ]
    
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Failed to capture screenshot for {url}.\nStderr: {res.stderr[:500]}")
    return output_path

def compute_diff(baseline_path, current_path, diff_output_path, sxs_output_path, threshold=25,
                 baseline_label="Baseline"):
    img_a = Image.open(baseline_path).convert("RGB")
    img_b = Image.open(current_path).convert("RGB")

    # Harmonize dimensions to maximum width & height
    max_w = max(img_a.width, img_b.width)
    max_h = max(img_a.height, img_b.height)

    canvas_a = Image.new("RGB", (max_w, max_h), (255, 255, 255))
    canvas_b = Image.new("RGB", (max_w, max_h), (255, 255, 255))
    canvas_a.paste(img_a, (0, 0))
    canvas_b.paste(img_b, (0, 0))

    # Vectorised pixel diff (C speed in Pillow) — the old per-pixel Python loop
    # took minutes on tall pages. delta = max(|dR|, |dG|, |dB|) > threshold.
    r, g, b = ImageChops.difference(canvas_a, canvas_b).split()
    delta = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mask = delta.point(lambda v: 255 if v > threshold else 0)
    diff_pixels = mask.histogram()[255]

    # Heatmap: dimmed grayscale baseline, differences in neon magenta
    heatmap = canvas_a.convert("L").point(lambda px: int(px * 0.35 + 40)).convert("RGB")
    heatmap.paste((255, 0, 127), (0, 0, max_w, max_h), mask)

    total_pixels = max_w * max_h
    mismatch_percent = (diff_pixels / total_pixels) * 100.0 if total_pixels > 0 else 0
    match_percent = 100.0 - mismatch_percent

    heatmap.save(diff_output_path, "PNG")
    
    # Create Side-by-Side Image
    header_h = 40
    sxs = Image.new("RGB", (max_w * 2 + 20, max_h + header_h), (240, 240, 239))
    draw = ImageDraw.Draw(sxs)
    
    # Paste Baseline and Current
    sxs.paste(canvas_a, (0, header_h))
    sxs.paste(canvas_b, (max_w + 20, header_h))
    
    # Add Header Labels
    draw.rectangle([(0, 0), (max_w, header_h)], fill=(10, 77, 84))
    draw.text((20, 12), f"BASELINE ({baseline_label})", fill=(255, 255, 255))
    
    draw.rectangle([(max_w + 20, 0), (max_w * 2 + 20, header_h)], fill=(29, 124, 124))
    draw.text((max_w + 40, 12), f"CURRENT (Local Upgraded) — Match: {match_percent:.1f}%", fill=(255, 255, 255))
    
    sxs.save(sxs_output_path, "PNG")
    
    return {
        "total_pixels": total_pixels,
        "diff_pixels": diff_pixels,
        "mismatch_percent": round(mismatch_percent, 2),
        "match_percent": round(match_percent, 2),
        "width": max_w,
        "height": max_h,
    }

def generate_html_report(results, report_path, path_slug):
    report_path = Path(report_path).resolve()
    
    viewports_json = json.dumps(results, indent=2)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visual Diff & PerfectPixel Report: {path_slug}</title>
    <style>
        :root {{
            --primary: #0284c7;
            --primary-dark: #0369a1;
            --bg: #0b0f19;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #f43f5e;
            --match-green: #10b981;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            padding: 24px;
            min-height: 100vh;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--card-bg);
            padding: 18px 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            border: 1px solid #334155;
        }}
        h1 {{
            font-family: 'Montserrat', sans-serif;
            font-size: 20px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .badge {{
            background: var(--primary);
            color: white;
            font-size: 12px;
            padding: 4px 10px;
            border-radius: 9999px;
            font-weight: 600;
        }}
        .controls {{
            display: flex;
            gap: 16px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .btn-group {{
            display: flex;
            background: #0F172A;
            border-radius: 8px;
            padding: 4px;
            border: 1px solid #334155;
        }}
        .btn {{
            background: transparent;
            color: var(--text-muted);
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
            transition: all 0.2s;
        }}
        .btn.active {{
            background: var(--primary);
            color: white;
        }}
        .stat-card {{
            display: flex;
            gap: 24px;
            background: var(--card-bg);
            padding: 16px 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            border: 1px solid #334155;
            align-items: center;
        }}
        .stat-item {{
            display: flex;
            flex-direction: column;
        }}
        .stat-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; }}
        .stat-value {{ font-size: 18px; font-weight: 700; color: white; }}
        .stat-value.highlight {{ color: var(--match-green); }}

        /* Viewer Container */
        .viewer-container {{
            background: var(--card-bg);
            border-radius: 12px;
            border: 1px solid #334155;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            overflow-x: auto;
        }}

        /* Slider PerfectPixel View */
        .slider-wrapper {{
            position: relative;
            overflow: hidden;
            border-radius: 8px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            user-select: none;
            max-width: 100%;
        }}
        .slider-wrapper img {{
            display: block;
            max-width: none;
        }}
        .img-before {{
            position: absolute;
            top: 0;
            left: 0;
            height: 100%;
            overflow: hidden;
            border-right: 2px solid #38BDF8;
        }}
        .slider-handle {{
            position: absolute;
            top: 0;
            bottom: 0;
            width: 4px;
            background: #38BDF8;
            cursor: ew-resize;
            transform: translateX(-50%);
        }}
        .slider-handle::after {{
            content: "↔";
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 32px;
            height: 32px;
            background: #38BDF8;
            color: #0F172A;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            box-shadow: 0 0 10px rgba(0,0,0,0.5);
        }}

        /* Onion Skin Overlay Mode */
        .onion-wrapper {{
            position: relative;
            display: none;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        }}
        .onion-wrapper .img-base {{
            display: block;
        }}
        .onion-wrapper .img-overlay {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            opacity: 0.5;
            pointer-events: none;
        }}

        /* Side-by-Side & Heatmap Mode */
        .image-mode-view {{
            display: none;
            max-width: 100%;
            border-radius: 8px;
            overflow: hidden;
        }}
        .image-mode-view img {{
            display: block;
            max-width: 100%;
            height: auto;
        }}

        .range-slider-container {{
            display: none;
            align-items: center;
            gap: 12px;
            margin-top: 16px;
            width: 300px;
        }}
        .range-slider-container input {{
            flex: 1;
        }}
    </style>
</head>
<body>

    <header>
        <h1>
            🎯 Visual Diff & PerfectPixel
            <span class="badge">{path_slug}</span>
        </h1>
        <div class="controls">
            <div class="btn-group" id="vp-selector">
                <!-- Dynamically populated -->
            </div>
            <div class="btn-group" id="mode-selector">
                <button class="btn active" data-mode="slider">🎚️ Split Swipe</button>
                <button class="btn" data-mode="onion">🧅 Onion Skin</button>
                <button class="btn" data-mode="heatmap">🔥 Heatmap Diff</button>
                <button class="btn" data-mode="sxs">↔️ Side by Side</button>
            </div>
        </div>
    </header>

    <div class="stat-card" id="stats-panel">
        <div class="stat-item">
            <span class="stat-label">Match Accuracy</span>
            <span class="stat-value highlight" id="stat-match">100%</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Mismatch Ratio</span>
            <span class="stat-value" id="stat-mismatch">0%</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Dimension</span>
            <span class="stat-value" id="stat-dim">1440 x 900</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Diff Pixels</span>
            <span class="stat-value" id="stat-pixels">0 px</span>
        </div>
    </div>

    <div class="viewer-container">
        <!-- Mode 1: Split Swipe Slider -->
        <div class="slider-wrapper" id="slider-view">
            <img id="img-after" src="" alt="Current Local">
            <div class="img-before" id="before-box">
                <img id="img-before" src="" alt="Baseline Live">
            </div>
            <div class="slider-handle" id="slider-handle"></div>
        </div>

        <!-- Mode 2: Onion Skin Overlay -->
        <div class="onion-wrapper" id="onion-view">
            <img class="img-base" id="onion-base" src="" alt="Baseline Live">
            <img class="img-overlay" id="onion-overlay" src="" alt="Current Local">
        </div>
        <div class="range-slider-container" id="onion-controls">
            <span>Baseline</span>
            <input type="range" id="opacity-slider" min="0" max="100" value="50">
            <span>Current</span>
        </div>

        <!-- Mode 3: Heatmap -->
        <div class="image-mode-view" id="heatmap-view">
            <img id="img-heatmap" src="" alt="Heatmap Diff">
        </div>

        <!-- Mode 4: Side-by-Side -->
        <div class="image-mode-view" id="sxs-view">
            <img id="img-sxs" src="" alt="Side-by-Side Diff">
        </div>
    </div>

    <script>
        const data = {viewports_json};
        const viewports = Object.keys(data);
        let currentVp = viewports[0];
        let currentMode = 'slider';

        // Populate Viewport Buttons
        const vpContainer = document.getElementById('vp-selector');
        viewports.forEach((vp, idx) => {{
            const btn = document.createElement('button');
            btn.className = 'btn' + (idx === 0 ? ' active' : '');
            btn.textContent = vp.toUpperCase() + ` (${{data[vp].width}}px)`;
            btn.addEventListener('click', () => setViewport(vp));
            vpContainer.appendChild(btn);
        }});

        // Mode Switching
        document.querySelectorAll('#mode-selector .btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                document.querySelectorAll('#mode-selector .btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                setMode(btn.dataset.mode);
            }});
        }});

        function setViewport(vp) {{
            currentVp = vp;
            document.querySelectorAll('#vp-selector .btn').forEach(b => {{
                b.classList.toggle('active', b.textContent.toLowerCase().startsWith(vp));
            }});
            updateViews();
        }}

        function setMode(mode) {{
            currentMode = mode;
            document.getElementById('slider-view').style.display = mode === 'slider' ? 'block' : 'none';
            document.getElementById('onion-view').style.display = mode === 'onion' ? 'block' : 'none';
            document.getElementById('onion-controls').style.display = mode === 'onion' ? 'flex' : 'none';
            document.getElementById('heatmap-view').style.display = mode === 'heatmap' ? 'block' : 'none';
            document.getElementById('sxs-view').style.display = mode === 'sxs' ? 'block' : 'none';
        }}

        function updateViews() {{
            const item = data[currentVp];
            if (!item) return;

            // Stats
            document.getElementById('stat-match').textContent = item.match_percent + '%';
            document.getElementById('stat-mismatch').textContent = item.mismatch_percent + '%';
            document.getElementById('stat-dim').textContent = `${{item.width}} x ${{item.height}}`;
            document.getElementById('stat-pixels').textContent = item.diff_pixels.toLocaleString() + ' px';

            // Slider
            document.getElementById('img-after').src = item.current_img;
            document.getElementById('img-before').src = item.baseline_img;
            document.getElementById('before-box').style.width = '50%';
            document.getElementById('slider-handle').style.left = '50%';

            // Onion Skin
            document.getElementById('onion-base').src = item.baseline_img;
            document.getElementById('onion-overlay').src = item.current_img;

            // Heatmap & SxS
            document.getElementById('img-heatmap').src = item.diff_img;
            document.getElementById('img-sxs').src = item.sxs_img;
        }}

        // Slider Interaction
        const sliderWrapper = document.getElementById('slider-view');
        const beforeBox = document.getElementById('before-box');
        const sliderHandle = document.getElementById('slider-handle');
        let isSliding = false;

        function updateSliderPosition(clientX) {{
            const rect = sliderWrapper.getBoundingClientRect();
            let x = clientX - rect.left;
            x = Math.max(0, Math.min(x, rect.width));
            const percent = (x / rect.width) * 100;
            beforeBox.style.width = percent + '%';
            sliderHandle.style.left = percent + '%';
        }}

        sliderWrapper.addEventListener('mousedown', () => isSliding = true);
        window.addEventListener('mouseup', () => isSliding = false);
        window.addEventListener('mousemove', (e) => {{
            if (!isSliding) return;
            updateSliderPosition(e.clientX);
        }});

        // Onion Skin Opacity Slider
        const opacitySlider = document.getElementById('opacity-slider');
        const onionOverlay = document.getElementById('onion-overlay');
        opacitySlider.addEventListener('input', (e) => {{
            onionOverlay.style.opacity = e.target.value / 100;
        }});

        // Initialize
        updateViews();
    </script>
</body>
</html>
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    return report_path

def main():
    hc.ensure_python()
    hc.enter_project_root()
    config = hc.load_config(quiet=True)

    default_baseline = os.environ.get("HYVA_BASELINE_URL") or config.get("baselineUrl") or ""
    default_target = os.environ.get("HYVA_TARGET_URL") or config.get("targetUrl") or ""
    default_viewports = ",".join(config.get("viewports") or ["desktop", "mobile"])

    parser = argparse.ArgumentParser(description="Automated Visual Diff & PerfectPixel Tool for Hyvä Theme Upgrade")
    parser.add_argument("path", nargs="?", default="",
                        help="Page path (e.g. contact or category/page.html) or full URL; empty = homepage")
    parser.add_argument("--baseline", default=default_baseline,
                        help="Baseline origin URL (default: config baselineUrl / $HYVA_BASELINE_URL)")
    parser.add_argument("--target", default=default_target,
                        help="Target origin URL (default: config targetUrl / $HYVA_TARGET_URL)")
    parser.add_argument("--viewports", default=default_viewports, help="Comma-separated: desktop, tablet, mobile")
    parser.add_argument("--height", type=int, default=0,
                        help="Override window height (px). Chrome only captures the window, so use e.g. 4000 "
                             "to include content below the fold")
    parser.add_argument("--threshold", type=int, default=25, help="Pixel difference color threshold (0-255)")
    parser.add_argument("--wait", type=int, default=4000, help="Wait time in ms for client JS/hydration")
    parser.add_argument("--output-dir", default="", help="Custom output directory (default: var/diffs/<slug>)")
    parser.add_argument("--fail-below", type=float, default=None,
                        help="Exit 1 if any viewport match percentage is below this threshold (e.g. 95.0)")
    args = parser.parse_args()

    if not args.baseline or not args.target:
        sys.stderr.write("❌ baselineUrl / targetUrl are not set. Fill them in .hyva-upgrade.json "
                         "or pass --baseline/--target.\n")
        sys.exit(2)

    try:
        chrome_bin = find_chrome()
    except RuntimeError as exc:
        sys.stderr.write(f"❌ {exc}\n")
        sys.exit(2)

    # Clean relative path
    rel_path = args.path.lstrip("/")
    if rel_path.startswith("http://") or rel_path.startswith("https://"):
        # Strip origin
        for prefix in [args.baseline, args.target]:
            if rel_path.startswith(prefix):
                rel_path = rel_path[len(prefix):].lstrip("/")
                break

    baseline_url = f"{args.baseline.rstrip('/')}/{rel_path}"
    target_url = f"{args.target.rstrip('/')}/{rel_path}"

    slug = rel_path.replace("/", "_").replace(".html", "").replace("?", "_").replace("=", "_") or "homepage"
    
    if args.output_dir:
        out_dir = Path(args.output_dir).resolve()
    else:
        out_dir = (hc.find_project_root() / "var" / "diffs" / slug).resolve()
    
    out_dir.mkdir(parents=True, exist_ok=True)

    requested_vps = [v.strip().lower() for v in args.viewports.split(",") if v.strip()]
    results = {}
    has_errors = False
    below_threshold = False

    print(f"\n=======================================================")
    print(f"🔍 Hyvä Visual Diff & PerfectPixel Tool")
    print(f"📍 Target Path : {rel_path}")
    print(f"🌐 Baseline    : {baseline_url}")
    print(f"💻 Local Target: {target_url}")
    print(f"📁 Output Dir  : {out_dir}")
    print(f"=======================================================\n")

    for vp_name in requested_vps:
        if vp_name not in VIEWPORT_PRESETS:
            print(f"⚠️ Unknown viewport '{vp_name}', skipping...")
            continue
        
        w, h = VIEWPORT_PRESETS[vp_name]
        if args.height:
            h = args.height
        print(f"📸 [{vp_name.upper()} {w}x{h}] Capturing screenshots...")
        
        base_img = out_dir / f"baseline_{vp_name}.png"
        target_img = out_dir / f"current_{vp_name}.png"
        diff_img = out_dir / f"diff_{vp_name}.png"
        sxs_img = out_dir / f"sxs_{vp_name}.png"

        try:
            capture_screenshot(chrome_bin, baseline_url, base_img, w, h, args.wait)
            capture_screenshot(chrome_bin, target_url, target_img, w, h, args.wait)
            
            print(f"⚖️ [{vp_name.upper()}] Computing pixel diff...")
            metrics = compute_diff(base_img, target_img, diff_img, sxs_img, args.threshold,
                                   baseline_label=urlparse(args.baseline).netloc or "baseline")
            
            metrics["baseline_img"] = base_img.name
            metrics["current_img"] = target_img.name
            metrics["diff_img"] = diff_img.name
            metrics["sxs_img"] = sxs_img.name
            
            results[vp_name] = metrics
            
            status_emoji = "✅" if metrics["match_percent"] >= 98.0 else ("⚠️" if metrics["match_percent"] >= 90.0 else "❌")
            print(f"   {status_emoji} Match Score: {metrics['match_percent']}% | Mismatch: {metrics['mismatch_percent']}% ({metrics['diff_pixels']:,} px)")
            if args.fail_below is not None and metrics["match_percent"] < args.fail_below:
                below_threshold = True
        except Exception as e:
            has_errors = True
            print(f"❌ [{vp_name.upper()}] Error: {e}")

    report_path = out_dir / "index.html"
    generate_html_report(results, report_path, slug)

    print(f"\n🎉 Visual Diff completed!")
    print(f"📊 Interactive Report: file://{report_path}")
    print(f"=======================================================\n")

    if has_errors or below_threshold:
        sys.exit(1)

if __name__ == "__main__":
    main()
