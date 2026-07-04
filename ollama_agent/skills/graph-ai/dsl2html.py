#!/usr/bin/env python3
"""dsl2html.py — Render graphai-dsl2image DSL to a single-page HTML file.

Generates a self-contained HTML file with embedded CSS, SVG arrows,
and interactive hover highlighting. No external dependencies.
"""

import sys
import os
import math
import json
import argparse

from dsl2image import parse_dsl, compute_node_widths, layout_nodes

# ---------- Theme Definitions ----------

THEMES = {
    'notebook': {
        'bg': '#faf8f0',
        'grid_minor': '#eae8e2',
        'grid_major': '#d2d0ca',
        'margin_line': '#d06060',
        'node_fill': '#fffff8',
        'node_border': '#2a2a2a',
        'node_border_w': 2,
        'node_shadow': 'rgba(0,0,0,0.08)',
        'node_shadow_hover': 'rgba(0,0,0,0.18)',
        'focus_fill': '#fffde0',
        'focus_border': '#1a5276',
        'focus_border_w': 3,
        'focus_text': '#1a5276',
        'text': '#1a1a1a',
        'arrow': '#2a2a2a',
        'free_arrow': '#8b4513',
        'title': '#4a4a4a',
        'title_text': 'dependency graph',
        'font': "'Comic Neue', 'Comic Sans MS', cursive",
        'font_size': 14,
        'border_radius': 4,
        'star_color': '#c77d00',
        'grid_type': 'notebook',
    },
    'ancient': {
        'bg': '#f0e4c8',
        'grid_minor': '#e8dcc0',
        'grid_major': '#d4c8a8',
        'margin_line': None,
        'node_fill': '#f5ecd4',
        'node_border': '#5c3a1e',
        'node_border_w': 2,
        'node_shadow': 'rgba(92,58,30,0.12)',
        'node_shadow_hover': 'rgba(92,58,30,0.25)',
        'focus_fill': '#e8d498',
        'focus_border': '#6b3a10',
        'focus_border_w': 3,
        'focus_text': '#6b3a10',
        'text': '#2c1a0a',
        'arrow': '#3e2510',
        'free_arrow': '#7a5c30',
        'title': '#7a6040',
        'title_text': 'lineage',
        'font': "'Crimson Pro', 'Georgia', serif",
        'font_size': 15,
        'border_radius': 3,
        'star_color': '#8b5a00',
        'grid_type': 'none',
    },
    'blueprint': {
        'bg': '#0d2b4a',
        'grid_minor': '#153d65',
        'grid_major': '#1a4a7a',
        'margin_line': None,
        'node_fill': '#14375a',
        'node_border': '#4a90d9',
        'node_border_w': 2,
        'node_shadow': 'rgba(74,144,217,0.15)',
        'node_shadow_hover': 'rgba(74,144,217,0.35)',
        'focus_fill': '#1a5276',
        'focus_border': '#7ec8e3',
        'focus_border_w': 3,
        'focus_text': '#7ec8e3',
        'text': '#c8e0f4',
        'arrow': '#4a90d9',
        'free_arrow': '#7ec8e3',
        'title': '#4a90d9',
        'title_text': 'blueprint',
        'font': "'JetBrains Mono', 'Consolas', 'Courier New', monospace",
        'font_size': 13,
        'border_radius': 8,
        'star_color': '#7ec8e3',
        'grid_type': 'blueprint',
    },
    'timeline': {
        'bg': '#f8f9fa',
        'grid_minor': None,
        'grid_major': None,
        'margin_line': None,
        'node_fill': '#ffffff',
        'node_border': '#4a6fa5',
        'node_border_w': 2,
        'node_shadow': 'rgba(74,111,165,0.12)',
        'node_shadow_hover': 'rgba(74,111,165,0.25)',
        'focus_fill': '#e8f0fe',
        'focus_border': '#1a73e8',
        'focus_border_w': 3,
        'focus_text': '#1a73e8',
        'text': '#2c3e50',
        'arrow': '#4a6fa5',
        'free_arrow': '#e67e22',
        'title': '#4a6fa5',
        'title_text': 'timeline',
        'font': "'Inter', 'Segoe UI', 'Helvetica Neue', sans-serif",
        'font_size': 14,
        'border_radius': 10,
        'star_color': '#1a73e8',
        'grid_type': 'none',
        'timeline_line': '#4a6fa5',
        'timeline_dot': '#4a6fa5',
        'timeline_dot_focus': '#1a73e8',
    },
}

# ---------- Arrow Routing ----------

def _box_exit_html(cx, cy, hw, hh, tx, ty, margin=4):
    dx, dy = tx - cx, ty - cy
    dist = math.hypot(dx, dy)
    if dist < 0.001:
        return cx, cy - hh - margin
    cos_a, sin_a = dx / dist, dy / dist
    t_x = (hw + margin) / abs(cos_a) if abs(cos_a) > 0.001 else 99999
    t_y = (hh + margin) / abs(sin_a) if abs(sin_a) > 0.001 else 99999
    t = min(t_x, t_y)
    return cx + t * cos_a, cy + t * sin_a

def _box_exit_vertical(cx, cy, hw, hh, tx, ty, margin=4):
    if ty >= cy:
        return cx, cy + hh + margin
    else:
        return cx, cy - hh - margin

# ---------- Layout Functions ----------

def _timeline_layout(nodes, tree_edges, h_gap=60, node_widths=None, bh=42):
    """Simple alternating timeline: nodes alternate above/below a horizontal line."""
    if node_widths is None:
        node_widths = compute_node_widths(nodes, min_w=140, char_w=8, pad=36)

    order = []
    in_degree = {nid: 0 for nid in nodes}
    children_of = {n: [] for n in nodes}
    has_parent = set()
    for f, t in tree_edges:
        if f in nodes and t in nodes:
            children_of[f].append(t)
            has_parent.add(t)
            in_degree[t] += 1

    roots = [n for n in nodes if n not in has_parent]
    if not roots:
        roots = list(nodes.keys())[:1]

    node_order = {nid: i for i, nid in enumerate(nodes)}
    from heapq import heappush, heappop
    queue = []
    for nid in nodes:
        if in_degree[nid] == 0:
            heappush(queue, (node_order.get(nid, 999), nid))
    while queue:
        _, nid = heappop(queue)
        order.append(nid)
        for child in children_of.get(nid, []):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                heappush(queue, (node_order.get(child, 999), child))
    for nid in nodes:
        if nid not in order:
            order.append(nid)

    margin_x = 80
    timeline_y = 300
    x = margin_x
    positions = {}
    for i, nid in enumerate(order):
        nw = node_widths[nid]
        cx = x + nw / 2
        if i % 2 == 0:
            cy = timeline_y - bh - 30
        else:
            cy = timeline_y + 30 + bh / 2
        positions[nid] = (cx, cy)
        x += nw + h_gap

    W = x + margin_x - h_gap
    H = timeline_y * 2 + 40
    return positions, order, W, H, timeline_y, roots


def _roadmap_layout(nodes, tree_edges, h_gap=60, node_widths=None, bh=42):
    """Fishbone roadmap: roots on spine, children branch at ~60 degree angles."""
    if node_widths is None:
        node_widths = compute_node_widths(nodes, min_w=140, char_w=8, pad=36)

    children_of = {n: [] for n in nodes}
    has_parent = set()
    parent_of = {}
    for f, t in tree_edges:
        if f in nodes and t in nodes:
            children_of[f].append(t)
            has_parent.add(t)
            parent_of[t] = f  # last parent wins

    children_of_single = {n: [] for n in nodes}
    for t, f in parent_of.items():
        children_of_single[f].append(t)

    roots = [n for n in nodes if n not in has_parent]
    if not roots:
        roots = list(nodes.keys())[:1]

    subtree_w = {}
    def get_subtree_width(nid):
        ch = children_of_single.get(nid, [])
        if not ch:
            subtree_w[nid] = node_widths[nid]
        else:
            children_total = sum(get_subtree_width(c) for c in ch) + max(0, len(ch) - 1) * 20
            subtree_w[nid] = max(node_widths[nid], children_total)
        return subtree_w[nid]
    for nid in nodes:
        if nid not in subtree_w:
            get_subtree_width(nid)

    margin_x = 80
    timeline_y = 300
    bone_angle = 60
    bone_dx = 80
    bone_dy = bone_dx * math.tan(math.radians(bone_angle))
    positions = {}
    order = []

    root_x = margin_x
    root_positions = {}
    for ri, root in enumerate(roots):
        rw = subtree_w[root]
        cx = root_x + rw / 2
        positions[root] = (cx, timeline_y)
        root_positions[root] = (cx, ri)
        order.append(root)
        root_x += rw + h_gap

    def place_branch(parent_id, parent_x, side, depth):
        ch = children_of_single.get(parent_id, [])
        if not ch:
            return
        unplaced = [c for c in ch if c not in positions]
        if not unplaced:
            return
        total_w = sum(subtree_w.get(child, node_widths[child]) for child in unplaced) + max(0, len(unplaced) - 1) * 20
        cx = parent_x - total_w / 2
        for child in unplaced:
            cw = subtree_w.get(child, node_widths[child])
            child_cx = cx + cw / 2
            child_y = timeline_y + side * (depth * bone_dy + bh + 10)
            positions[child] = (child_cx, child_y)
            order.append(child)
            place_branch(child, child_cx, side, depth + 1)
            cx += cw + 20

    for root in roots:
        ri = root_positions[root][1]
        side = -1 if ri % 2 == 0 else 1
        place_branch(root, root_positions[root][0], side, 1)

    for nid in nodes:
        if nid not in positions:
            positions[nid] = (margin_x, timeline_y)
            order.append(nid)

    if positions:
        min_x = min(x - node_widths[n] / 2 for n, (x, y) in positions.items())
        max_x = max(x + node_widths[n] / 2 for n, (x, y) in positions.items())
        min_y = min(y - bh / 2 for n, (x, y) in positions.items())
        max_y = max(y + bh / 2 for n, (x, y) in positions.items())
        W = int(max_x - min_x + 2 * margin_x)
        H = int(max_y - min_y + 2 * margin_x)
        shift_x = margin_x - min_x
        shift_y = margin_x - min_y
        positions = {n: (x + shift_x, y + shift_y) for n, (x, y) in positions.items()}
        timeline_y += shift_y
        root_positions = {r: (x + shift_x, ri) for r, (x, ri) in root_positions.items()}
    else:
        W, H = 600, 400

    return positions, order, W, H, timeline_y, roots, root_positions


def _fishbone_layout(nodes, tree_edges, h_gap=60, node_widths=None, bh=42):
    """Fishbone (Ishikawa) layout: spine with diagonal bones, fish head at right."""
    if node_widths is None:
        node_widths = compute_node_widths(nodes, min_w=140, char_w=8, pad=36)

    children_of = {n: [] for n in nodes}
    has_parent = set()
    parent_of = {}
    for f, t in tree_edges:
        if f in nodes and t in nodes:
            children_of[f].append(t)
            has_parent.add(t)
            parent_of[t] = f

    children_of_single = {n: [] for n in nodes}
    for t, f in parent_of.items():
        children_of_single[f].append(t)

    roots = [n for n in nodes if n not in has_parent]
    if not roots:
        roots = list(nodes.keys())[:1]

    margin_x = 80
    spine_y = 300
    bone_angle = 60
    bone_dx = 120
    bone_dy = bone_dx * math.tan(math.radians(bone_angle))
    spine_spacing = 220

    positions = {}
    order = []
    root_spine_x = {}

    spine_start_x = margin_x + 100
    for i, root in enumerate(roots):
        sx = spine_start_x + i * spine_spacing
        root_spine_x[root] = sx
        side = -1 if i % 2 == 0 else 1
        rx = sx + bone_dx
        ry = spine_y + side * bone_dy
        positions[root] = (rx, ry)
        order.append(root)

        ch = children_of_single.get(root, [])
        for j, child in enumerate(ch):
            cx = rx + (j + 1) * bone_dx * 0.7
            cy = ry + side * (j + 1) * bone_dy * 0.3
            positions[child] = (cx, cy)
            order.append(child)
            for k, gc in enumerate(children_of_single.get(child, [])):
                gcx = cx + (k + 1) * bone_dx * 0.4
                gcy = cy + side * (k + 1) * bone_dy * 0.15
                positions[gc] = (gcx, gcy)
                order.append(gc)

    for nid in nodes:
        if nid not in positions:
            positions[nid] = (margin_x, spine_y)
            order.append(nid)

    if positions:
        min_x = min(x - node_widths[n] / 2 for n, (x, y) in positions.items())
        max_x = max(x + node_widths[n] / 2 for n, (x, y) in positions.items())
        min_y = min(y - bh / 2 for n, (x, y) in positions.items())
        max_y = max(y + bh / 2 for n, (x, y) in positions.items())
        W = int(max_x - min_x + 2 * margin_x)
        H = int(max_y - min_y + 2 * margin_x)
        shift_x = margin_x - min_x
        shift_y = margin_x - min_y
        positions = {n: (x + shift_x, y + shift_y) for n, (x, y) in positions.items()}
        spine_y += shift_y
        root_spine_x = {r: x + shift_x for r, x in root_spine_x.items()}
        spine_start_x += shift_x
    else:
        W, H = 600, 400

    spine_end_x = max(x for x, y in positions.values()) + 80 if positions else W - margin_x
    return positions, order, W, H, spine_y, roots, root_spine_x, spine_start_x, spine_end_x


# ---------- Shared HTML Template ----------

def _html_template(theme, W, H, svg_elements, nodes_html, connections, title_text, output_path, extra_css=''):
    bg_css = ''
    grid_type = theme.get('grid_type', 'none')
    if grid_type == 'notebook':
        bg_css = f"""\
    .diagram-container::before {{
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background-image:
        linear-gradient({theme['grid_major']} 1px, transparent 1px),
        linear-gradient(90deg, {theme['grid_major']} 1px, transparent 1px),
        linear-gradient({theme['grid_minor']} 1px, transparent 1px),
        linear-gradient(90deg, {theme['grid_minor']} 1px, transparent 1px);
      background-size: 50px 50px, 50px 50px, 10px 10px, 10px 10px;
      z-index: 0;
    }}
    .diagram-container::after {{
      content: '';
      position: absolute;
      top: 0; left: 30px;
      width: 2px; height: 100%;
      background: {theme['margin_line']};
      z-index: 0;
    }}"""
    elif grid_type == 'blueprint':
        bg_css = f"""\
    .diagram-container::before {{
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background-image:
        linear-gradient({theme['grid_major']} 1px, transparent 1px),
        linear-gradient(90deg, {theme['grid_major']} 1px, transparent 1px),
        linear-gradient({theme['grid_minor']} 1px, transparent 1px),
        linear-gradient(90deg, {theme['grid_minor']} 1px, transparent 1px);
      background-size: 50px 50px, 50px 50px, 10px 10px, 10px 10px;
      z-index: 0;
    }}"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_text or 'Diagram'}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Comic+Neue:wght@400;700&family=Crimson+Pro:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: {theme['bg']};
    font-family: {theme['font']};
    overflow: auto;
    min-width: fit-content;
    padding: 20px;
  }}
  .diagram-container {{
    position: relative;
    width: {W}px;
    height: {H}px;
    flex-shrink: 0;
  }}
{bg_css}
{extra_css}
  .node {{
    position: absolute;
    text-align: center;
    display: flex;
    align-items: center;
    justify-content: center;
    border: {theme['node_border_w']}px solid {theme['node_border']};
    background: {theme['node_fill']};
    border-radius: {theme['border_radius']}px;
    font-size: {theme['font_size']}px;
    color: {theme['text']};
    padding: 4px 10px;
    box-shadow: 2px 2px 6px {theme['node_shadow']};
    cursor: default;
    transition: box-shadow 0.2s, transform 0.15s, opacity 0.2s;
    z-index: 2;
    line-height: 1.3;
    user-select: none;
  }}
  .node:hover {{
    box-shadow: 3px 3px 12px {theme['node_shadow_hover']};
    transform: translateY(-1px);
    z-index: 10;
  }}
  .node.focus {{
    background: {theme['focus_fill']};
    border-color: {theme['focus_border']};
    border-width: {theme['focus_border_w']}px;
    color: {theme['focus_text']};
    font-weight: 600;
  }}
  .node.focus::before {{
    content: '\\2605 ';
    color: {theme['star_color']};
  }}
  .arrows-svg {{
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
    z-index: 1;
    pointer-events: none;
  }}
  .arrow-line {{
    transition: opacity 0.2s, stroke-width 0.2s;
  }}
  .title {{
    position: absolute;
    top: 12px; right: 20px;
    font-size: {theme['font_size'] + 2}px;
    color: {theme['title']};
    opacity: 0.6;
    z-index: 3;
    pointer-events: none;
  }}
  .toolbar {{
    position: fixed;
    top: 16px;
    right: 16px;
    display: flex;
    gap: 8px;
    z-index: 100;
  }}
  .toolbar button {{
    padding: 8px 16px;
    border: 1px solid {theme['node_border']};
    border-radius: 6px;
    background: {theme['node_fill']};
    color: {theme['text']};
    font-family: {theme['font']};
    font-size: 13px;
    cursor: pointer;
    box-shadow: 1px 1px 4px {theme['node_shadow']};
    transition: background 0.2s, transform 0.1s;
  }}
  .toolbar button:hover {{
    background: {theme['focus_fill']};
    transform: translateY(-1px);
  }}
  .toolbar button:active {{
    transform: translateY(0);
  }}
  .toolbar button:disabled {{
    opacity: 0.5;
    cursor: not-allowed;
  }}
</style>
</head>
<body>
<div class="toolbar">
  <button id="btn-copy" onclick="copyToClipboard()">&#128203; Copy Image</button>
  <button id="btn-download" onclick="downloadPNG()">&#11015; Download PNG</button>
</div>
<div class="diagram-container">
  <svg class="arrows-svg" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <marker id="arrowhead" markerWidth="12" markerHeight="8" refX="0" refY="4" orient="auto" markerUnits="userSpaceOnUse">
        <polygon points="0 0, 12 4, 0 8" fill="{theme['arrow']}" />
      </marker>
      <marker id="free-arrowhead" markerWidth="12" markerHeight="8" refX="0" refY="4" orient="auto" markerUnits="userSpaceOnUse">
        <polygon points="0 0, 12 4, 0 8" fill="{theme['free_arrow']}" />
      </marker>
    </defs>
    {chr(10).join(svg_elements)}
  </svg>
  {chr(10).join(nodes_html)}
  <div class="title">{title_text}</div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script>
  const connections = {json.dumps(connections)};
  document.querySelectorAll('.node').forEach(node => {{
    node.addEventListener('mouseenter', () => {{
      const id = node.dataset.id;
      const connected = new Set(connections[id] || []);
      connected.add(id);
      document.querySelectorAll('.node').forEach(n => {{
        if (!connected.has(n.dataset.id)) {{
          n.style.opacity = '0.25';
        }}
      }});
      document.querySelectorAll('.arrow-line').forEach(line => {{
        const from = line.dataset.from;
        const to = line.dataset.to;
        if (from !== id && to !== id) {{
          line.style.opacity = '0.15';
        }} else {{
          line.style.strokeWidth = '3';
        }}
      }});
    }});
    node.addEventListener('mouseleave', () => {{
      document.querySelectorAll('.node').forEach(n => {{
        n.style.opacity = '1';
      }});
      document.querySelectorAll('.arrow-line').forEach(line => {{
        line.style.strokeWidth = line.dataset.width;
        line.style.opacity = '1';
      }});
    }});
  }});

  async function captureDiagram() {{
    const container = document.querySelector('.diagram-container');
    document.querySelectorAll('.node').forEach(n => n.style.opacity = '1');
    document.querySelectorAll('.arrow-line').forEach(l => {{
      l.style.strokeWidth = l.dataset.width;
      l.style.opacity = '1';
    }});
    const canvas = await html2canvas(container, {{
      backgroundColor: '{theme["bg"]}',
      scale: 2,
      useCORS: true,
      logging: false
    }});
    return canvas;
  }}

  async function copyToClipboard() {{
    const btn = document.getElementById('btn-copy');
    btn.disabled = true;
    btn.textContent = 'Copying...';
    try {{
      const canvas = await captureDiagram();
      canvas.toBlob(async (blob) => {{
        try {{
          await navigator.clipboard.write([new ClipboardItem({{'image/png': blob}})]);
          btn.textContent = '✓ Copied!';
        }} catch (e) {{
          const url = URL.createObjectURL(blob);
          window.open(url, '_blank');
          btn.textContent = 'Opened in tab';
        }}
        setTimeout(() => {{ btn.textContent = '📋 Copy Image'; btn.disabled = false; }}, 2000);
      }});
    }} catch (e) {{
      console.error(e);
      btn.textContent = '✗ Failed';
      setTimeout(() => {{ btn.textContent = '📋 Copy Image'; btn.disabled = false; }}, 2000);
    }}
  }}

  async function downloadPNG() {{
    const btn = document.getElementById('btn-download');
    btn.disabled = true;
    btn.textContent = 'Rendering...';
    try {{
      const canvas = await captureDiagram();
      const link = document.createElement('a');
      link.download = '{os.path.splitext(os.path.basename(output_path))[0]}.png';
      link.href = canvas.toDataURL('image/png');
      link.click();
      btn.textContent = '✓ Downloaded!';
    }} catch (e) {{
      console.error(e);
      btn.textContent = '✗ Failed';
    }}
    setTimeout(() => {{ btn.textContent = '⬇ Download PNG'; btn.disabled = false; }}, 2000);
  }}
</script>
</body>
</html>"""
    return html


# ---------- Generate Functions ----------

def generate_html(nodes, tree_edges, free_edges, output_path, focus=None, style='notebook', title=None, annotations=None):
    theme = THEMES.get(style, THEMES['notebook'])
    node_widths = compute_node_widths(nodes, min_w=140, char_w=8, pad=36)
    bh = 42
    avg_w = sum(node_widths.values()) / len(node_widths) if node_widths else 200
    tw = max(1000, len(nodes) * int(avg_w + 20))
    th = 1400
    positions, layers, node_widths, bh, vg = layout_nodes(nodes, tree_edges, tw, th, node_widths=node_widths)
    hh = bh / 2

    margin = 60
    if positions:
        min_x = min(x - node_widths[n] / 2 for n, (x, y) in positions.items())
        max_x = max(x + node_widths[n] / 2 for n, (x, y) in positions.items())
        min_y = min(y - hh for n, (x, y) in positions.items())
        max_y = max(y + hh for n, (x, y) in positions.items())
        W = int(max_x - min_x + 2 * margin)
        H = int(max_y - min_y + 2 * margin)
        shift_x = margin - min_x
        shift_y = margin - min_y
        positions = {n: (x + shift_x, y + shift_y) for n, (x, y) in positions.items()}
    else:
        W, H = 600, 400

    connections = {nid: [] for nid in nodes}
    for f, t in tree_edges:
        connections.setdefault(f, []).append(t)
        connections.setdefault(t, []).append(f)
    for f, t in free_edges:
        connections.setdefault(f, []).append(t)
        connections.setdefault(t, []).append(f)
    for nid in connections:
        connections[nid] = list(set(connections[nid]))

    arrow_head_len = 12
    svg_paths = []
    for fi, ti in tree_edges:
        if fi not in positions or ti not in positions:
            continue
        fx, fy = positions[fi]
        tx, ty = positions[ti]
        sx, sy = _box_exit_vertical(fx, fy, node_widths[fi] / 2, hh, tx, ty)
        ex, ey = _box_exit_vertical(tx, ty, node_widths[ti] / 2, hh, fx, fy)
        if ey > sy:
            ey_line = ey - arrow_head_len
        else:
            ey_line = ey + arrow_head_len
        mid_y = (sy + ey) / 2
        d = f"M{sx:.1f},{sy:.1f} C{sx:.1f},{mid_y:.1f} {ex:.1f},{mid_y:.1f} {ex:.1f},{ey_line:.1f}"
        svg_paths.append(
            f'<path class="arrow-line" data-from="{fi}" data-to="{ti}" '
            f'data-width="2" d="{d}" '
            f'stroke="{theme["arrow"]}" stroke-width="2" fill="none" marker-end="url(#arrowhead)" />'
        )

    for fi, ti in free_edges:
        if fi not in positions or ti not in positions:
            continue
        fx, fy = positions[fi]
        tx, ty = positions[ti]
        sx, sy = _box_exit_html(fx, fy, node_widths[fi] / 2, hh, tx, ty)
        ex, ey = _box_exit_html(tx, ty, node_widths[ti] / 2, hh, fx, fy)
        dx, dy = ex - sx, ey - sy
        dist = math.hypot(dx, dy)
        if dist > arrow_head_len:
            ex_line = ex - dx / dist * arrow_head_len
            ey_line = ey - dy / dist * arrow_head_len
        else:
            ex_line, ey_line = ex, ey
        d = f"M{sx:.1f},{sy:.1f} L{ex_line:.1f},{ey_line:.1f}"
        svg_paths.append(
            f'<path class="arrow-line" data-from="{fi}" data-to="{ti}" '
            f'data-width="2" d="{d}" '
            f'stroke="{theme["free_arrow"]}" stroke-width="2" fill="none" '
            f'stroke-dasharray="8,5" marker-end="url(#free-arrowhead)" />'
        )

    nodes_html = []
    for nid, label in nodes.items():
        if nid not in positions:
            continue
        x, y = positions[nid]
        nw = node_widths[nid]
        left = x - nw / 2
        top = y - hh
        is_focus = (focus is not None and nid == focus)
        cls = 'node focus' if is_focus else 'node'
        label_esc = label.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        ann = annotations.get(nid, '') if annotations else ''
        title_attr = f' title="{ann}"' if ann else ''
        nodes_html.append(
            f'<div class="{cls}" data-id="{nid}"{title_attr} '
            f'style="left:{left:.1f}px; top:{top:.1f}px; width:{nw:.0f}px; height:{bh}px;">'
            f'{label_esc}</div>'
        )

    title_text = title or theme.get('title_text', '')
    html = _html_template(theme, W, H, svg_paths, nodes_html, connections, title_text, output_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"HTML saved to: {output_path}")
    return output_path


def generate_timeline_html(nodes, tree_edges, free_edges, output_path, focus=None, style='timeline', title=None, annotations=None):
    theme = THEMES.get(style, THEMES['timeline'])
    node_widths = compute_node_widths(nodes, min_w=140, char_w=8, pad=36)
    bh = 42
    hh = bh / 2

    positions, order, W, H, timeline_y, roots = _timeline_layout(
        nodes, tree_edges, h_gap=60, node_widths=node_widths, bh=bh
    )

    connections = {nid: [] for nid in nodes}
    for f, t in tree_edges:
        connections.setdefault(f, []).append(t)
        connections.setdefault(t, []).append(f)
    for f, t in free_edges:
        connections.setdefault(f, []).append(t)
        connections.setdefault(t, []).append(f)
    for nid in connections:
        connections[nid] = list(set(connections[nid]))

    svg_elements = []
    line_color = theme.get('timeline_line', '#4a6fa5')
    dot_color = theme.get('timeline_dot', '#4a6fa5')
    dot_focus = theme.get('timeline_dot_focus', '#1a73e8')
    arrow_head_len = 12

    first_x = positions[order[0]][0] if order else 0
    last_x = positions[order[-1]][0] if order else 0
    svg_elements.append(
        f'<line x1="{first_x - 30:.1f}" y1="{timeline_y}" x2="{last_x + 30:.1f}" y2="{timeline_y}" '
        f'stroke="{line_color}" stroke-width="3" stroke-linecap="round" />'
    )

    for nid in order:
        if nid not in positions:
            continue
        cx, cy = positions[nid]
        is_focus = (focus is not None and nid == focus)
        dc = dot_focus if is_focus else dot_color
        r = 7 if is_focus else 5
        svg_elements.append(f'<circle cx="{cx:.1f}" cy="{timeline_y}" r="{r}" fill="{dc}" />')
        node_top_or_bottom = timeline_y - 22 if cy < timeline_y else timeline_y + 22
        svg_elements.append(
            f'<line x1="{cx:.1f}" y1="{timeline_y}" x2="{cx:.1f}" y2="{node_top_or_bottom:.1f}" '
            f'stroke="{line_color}" stroke-width="1.5" stroke-dasharray="4,3" />'
        )

    for i in range(len(order) - 1):
        nid_from = order[i]
        nid_to = order[i + 1]
        if nid_from not in positions or nid_to not in positions:
            continue
        x1 = positions[nid_from][0] + node_widths[nid_from] / 2 + 4
        x2 = positions[nid_to][0] - node_widths[nid_to] / 2 - 4 - arrow_head_len
        if x2 > x1:
            svg_elements.append(
                f'<path class="arrow-line" data-from="{nid_from}" data-to="{nid_to}" '
                f'data-width="2" d="M{x1:.1f},{timeline_y} L{x2:.1f},{timeline_y}" '
                f'stroke="{theme["arrow"]}" stroke-width="2" fill="none" marker-end="url(#arrowhead)" />'
            )

    nodes_html = []
    for nid in order:
        if nid not in positions:
            continue
        x, y = positions[nid]
        nw = node_widths[nid]
        left = x - nw / 2
        top = y - hh
        is_focus = (focus is not None and nid == focus)
        cls = 'node focus' if is_focus else 'node'
        label_esc = nodes[nid].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        ann = annotations.get(nid, '') if annotations else ''
        title_attr = f' title="{ann}"' if ann else ''
        nodes_html.append(
            f'<div class="{cls}" data-id="{nid}"{title_attr} '
            f'style="left:{left:.1f}px; top:{top:.1f}px; width:{nw:.0f}px; height:{bh}px;">'
            f'{label_esc}</div>'
        )

    title_text = title or theme.get('title_text', '')
    html = _html_template(theme, W, H, svg_elements, nodes_html, connections, title_text, output_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"HTML saved to: {output_path}")
    return output_path


def generate_roadmap_html(nodes, tree_edges, free_edges, output_path, focus=None, style='roadmap', title=None, annotations=None):
    theme = THEMES.get('timeline', THEMES['timeline'])
    node_widths = compute_node_widths(nodes, min_w=140, char_w=8, pad=36)
    bh = 42
    hh = bh / 2

    positions, order, W, H, timeline_y, roots, root_positions = _roadmap_layout(
        nodes, tree_edges, h_gap=60, node_widths=node_widths, bh=bh
    )

    connections = {nid: [] for nid in nodes}
    for f, t in tree_edges:
        connections.setdefault(f, []).append(t)
        connections.setdefault(t, []).append(f)
    for f, t in free_edges:
        connections.setdefault(f, []).append(t)
        connections.setdefault(t, []).append(f)
    for nid in connections:
        connections[nid] = list(set(connections[nid]))

    svg_elements = []
    line_color = theme.get('timeline_line', '#4a6fa5')
    dot_color = theme.get('timeline_dot', '#4a6fa5')
    dot_focus = theme.get('timeline_dot_focus', '#1a73e8')
    arrow_head_len = 12

    parent_of = {}
    for f, t in tree_edges:
        if f in positions and t in positions:
            parent_of[t] = f

    root_xs = [positions[r][0] for r in roots if r in positions]
    if root_xs:
        first_x = min(root_xs) - 30
        last_x = max(root_xs) + 30
        svg_elements.append(
            f'<line x1="{first_x:.1f}" y1="{timeline_y}" x2="{last_x:.1f}" y2="{timeline_y}" '
            f'stroke="{line_color}" stroke-width="3" stroke-linecap="round" />'
        )

    for i in range(len(roots) - 1):
        r1, r2 = roots[i], roots[i + 1]
        if r1 in positions and r2 in positions:
            x1 = positions[r1][0] + node_widths[r1] / 2 + 4
            x2 = positions[r2][0] - node_widths[r2] / 2 - 4 - arrow_head_len
            if x2 > x1:
                svg_elements.append(
                    f'<path class="arrow-line" data-from="{r1}" data-to="{r2}" '
                    f'data-width="2" d="M{x1:.1f},{timeline_y} L{x2:.1f},{timeline_y}" '
                    f'stroke="{theme["arrow"]}" stroke-width="2" fill="none" marker-end="url(#arrowhead)" />'
                )

    for nid in order:
        if nid not in positions:
            continue
        cx, cy = positions[nid]
        is_focus = (focus is not None and nid == focus)
        dc = dot_focus if is_focus else dot_color
        r = 7 if is_focus else 5

        if nid in [r for r in roots]:
            svg_elements.append(f'<circle cx="{cx:.1f}" cy="{timeline_y}" r="{r}" fill="{dc}" />')
            node_edge_y = timeline_y - 22 if cy < timeline_y else timeline_y + 22
            svg_elements.append(
                f'<line x1="{cx:.1f}" y1="{timeline_y}" x2="{cx:.1f}" y2="{node_edge_y:.1f}" '
                f'stroke="{line_color}" stroke-width="1.5" stroke-dasharray="4,3" />'
            )
        elif nid in parent_of:
            pid = parent_of[nid]
            if pid in positions:
                px, py = positions[pid]
                if cy < py:
                    sy = py - bh / 2 - 2
                    ey = cy + bh / 2 + 2 + arrow_head_len
                else:
                    sy = py + bh / 2 + 2
                    ey = cy - bh / 2 - 2 - arrow_head_len
                svg_elements.append(
                    f'<path class="arrow-line" data-from="{pid}" data-to="{nid}" '
                    f'data-width="2" d="M{px:.1f},{sy:.1f} L{cx:.1f},{ey:.1f}" '
                    f'stroke="{theme["arrow"]}" stroke-width="2" fill="none" marker-end="url(#arrowhead)" />'
                )

    nodes_html = []
    for nid in order:
        if nid not in positions:
            continue
        x, y = positions[nid]
        nw = node_widths[nid]
        left = x - nw / 2
        top = y - hh
        is_focus = (focus is not None and nid == focus)
        cls = 'node focus' if is_focus else 'node'
        label_esc = nodes[nid].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        ann = annotations.get(nid, '') if annotations else ''
        title_attr = f' title="{ann}"' if ann else ''
        nodes_html.append(
            f'<div class="{cls}" data-id="{nid}"{title_attr} '
            f'style="left:{left:.1f}px; top:{top:.1f}px; width:{nw:.0f}px; height:{bh}px;">'
            f'{label_esc}</div>'
        )

    title_text = title or 'roadmap'
    html = _html_template(theme, W, H, svg_elements, nodes_html, connections, title_text, output_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"HTML saved to: {output_path}")
    return output_path


def generate_fishbone_html(nodes, tree_edges, free_edges, output_path, focus=None, style='fishbone', title=None, annotations=None):
    theme = THEMES.get('timeline', THEMES['timeline'])
    node_widths = compute_node_widths(nodes, min_w=140, char_w=8, pad=36)
    bh = 42
    hh = bh / 2

    positions, order, W, H, spine_y, roots, root_spine_x, spine_start_x, spine_end_x = _fishbone_layout(
        nodes, tree_edges, h_gap=60, node_widths=node_widths, bh=bh
    )

    parent_of = {}
    for f, t in tree_edges:
        if f in positions and t in positions:
            parent_of[t] = f

    connections = {nid: [] for nid in nodes}
    for f, t in tree_edges:
        connections.setdefault(f, []).append(t)
        connections.setdefault(t, []).append(f)
    for f, t in free_edges:
        connections.setdefault(f, []).append(t)
        connections.setdefault(t, []).append(f)
    for nid in connections:
        connections[nid] = list(set(connections[nid]))

    svg_elements = []
    line_color = theme.get('timeline_line', '#4a6fa5')
    dot_color = theme.get('timeline_dot', '#4a6fa5')
    dot_focus = theme.get('timeline_dot_focus', '#1a73e8')

    # Spine: horizontal line with arrowhead
    svg_elements.append(
        f'<line x1="{spine_start_x - 20:.1f}" y1="{spine_y}" x2="{spine_end_x:.1f}" y2="{spine_y}" '
        f'stroke="{line_color}" stroke-width="3" stroke-linecap="round" />'
    )
    svg_elements.append(
        f'<polygon points="{spine_end_x:.1f},{spine_y} {spine_end_x - 12:.1f},{spine_y - 6:.1f} {spine_end_x - 12:.1f},{spine_y + 6:.1f}" fill="{line_color}" />'
    )

    # Fish head: title box at right end
    title_text = title or theme.get('title_text', '')
    if title_text:
        tw = len(title_text) * 8 + 30
        head_x = spine_end_x + 10
        head_y = spine_y - bh / 2
        svg_elements.append(
            f'<rect x="{head_x:.1f}" y="{head_y:.1f}" width="{tw:.0f}" height="{bh:.0f}" '
            f'rx="6" ry="6" fill="{theme["focus_fill"]}" stroke="{theme["focus_border"]}" stroke-width="2" />'
        )
        svg_elements.append(
            f'<text x="{head_x + tw/2:.1f}" y="{spine_y + 1:.1f}" text-anchor="middle" dominant-baseline="central" '
            f'font-family="{theme["font"]}" font-size="{theme["font_size"]}px" fill="{theme["focus_text"]}" font-weight="600">'
            f'{title_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</text>'
        )

    # Bones: diagonal lines from spine to roots, and from roots to children
    for nid in order:
        if nid not in positions:
            continue
        cx, cy = positions[nid]
        is_focus = (focus is not None and nid == focus)

        if nid in root_spine_x:
            sx = root_spine_x[nid]
            svg_elements.append(
                f'<line x1="{sx:.1f}" y1="{spine_y}" x2="{cx:.1f}" y2="{cy:.1f}" '
                f'stroke="{line_color}" stroke-width="2" />'
            )
            svg_elements.append(
                f'<circle cx="{sx:.1f}" cy="{spine_y}" r="4" fill="{dot_focus if is_focus else dot_color}" />'
            )
        elif nid in parent_of:
            pid = parent_of[nid]
            if pid in positions:
                px, py = positions[pid]
                svg_elements.append(
                    f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{cx:.1f}" y2="{cy:.1f}" '
                    f'stroke="{theme["arrow"]}" stroke-width="1.5" />'
                )

    nodes_html = []
    for nid in order:
        if nid not in positions:
            continue
        x, y = positions[nid]
        nw = node_widths[nid]
        left = x - nw / 2
        top = y - hh
        is_focus = (focus is not None and nid == focus)
        cls = 'node focus' if is_focus else 'node'
        label_esc = nodes[nid].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        ann = annotations.get(nid, '') if annotations else ''
        title_attr = f' title="{ann}"' if ann else ''
        nodes_html.append(
            f'<div class="{cls}" data-id="{nid}"{title_attr} '
            f'style="left:{left:.1f}px; top:{top:.1f}px; width:{nw:.0f}px; height:{bh}px;">'
            f'{label_esc}</div>'
        )

    html = _html_template(theme, W, H, svg_elements, nodes_html, connections, title_text, output_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"HTML saved to: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Render graphai-dsl2image DSL to HTML')
    parser.add_argument('input', help='DSL file path, or inline DSL text with --dsl')
    parser.add_argument('output', nargs='?', default=None, help='Output HTML path (default: same name as input)')
    parser.add_argument('--dsl', action='store_true', help='Treat input as inline DSL text')
    parser.add_argument('--style', choices=['notebook', 'ancient', 'blueprint', 'timeline', 'roadmap', 'fishbone'], default=None,
                        help='Visual style. Overrides DSL style= directive.')
    args = parser.parse_args()

    if args.dsl:
        dsl_text = args.input
        out = args.output or 'diagram_output.html'
    else:
        with open(args.input, 'r', encoding='utf-8') as f:
            dsl_text = f.read()
        out = args.output or os.path.join(os.getcwd(), os.path.splitext(os.path.basename(args.input))[0] + '.html')

    nodes, te, fe, focus, dsl_style, dsl_title, annotations = parse_dsl(dsl_text)
    style = args.style or dsl_style or 'notebook'

    if style == 'timeline':
        generate_timeline_html(nodes, te, fe, out, focus=focus, style=style, title=dsl_title, annotations=annotations)
    elif style == 'roadmap':
        generate_roadmap_html(nodes, te, fe, out, focus=focus, style=style, title=dsl_title, annotations=annotations)
    elif style == 'fishbone':
        from dsl2fishbone import generate_fishbone_html as _gen_fishbone
        _gen_fishbone(nodes, te, fe, out, focus=focus, title=dsl_title, annotations=annotations)
    else:
        generate_html(nodes, te, fe, out, focus=focus, style=style, title=dsl_title, annotations=annotations)


if __name__ == '__main__':
    main()
