#!/usr/bin/env python3
"""dsl2fishbone.py — Fishbone (Ishikawa) diagram renderer for graphai-dsl.

Self-contained: imports from dsl2image for parsing only, generates its own HTML.
Does NOT modify dsl2html.py — fully isolated to avoid breaking existing styles.
"""
import sys, os, math, json, argparse
from dsl2image import parse_dsl, compute_node_widths

THEME = {
    'bg': '#fbfbfc', 'grid_minor': '#d0d5dd',
    'node_fill': '#ffffff', 'node_border': '#4a6fa5', 'node_border_w': 2,
    'node_shadow': 'rgba(74,111,165,0.10)', 'node_shadow_hover': 'rgba(74,111,165,0.22)',
    'focus_fill': '#e8f0fe', 'focus_border': '#1a73e8', 'focus_border_w': 3,
    'focus_text': '#1a73e8', 'text': '#2c3e50', 'arrow': '#4a6fa5',
    'free_arrow': '#00ff00', 'title': '#4a6fa5',
    'font': "'Inter','Segoe UI','Helvetica Neue',sans-serif", 'font_size': 14,
    'border_radius': 10, 'star_color': '#1a73e8',
    'timeline_line': '#4a6fa5', 'timeline_dot': '#4a6fa5', 'timeline_dot_focus': '#1a73e8',
}


def _fishbone_layout(nodes, tree_edges, node_widths, bh=42):
    """Roots ON spine, children alternate above/below, recursive depth, 60° inclination."""
    children_of = {n: [] for n in nodes}; has_parent = set()
    for f, t in tree_edges:
        if f in nodes and t in nodes: children_of[f].append(t); has_parent.add(t)
    roots = [n for n in nodes if n not in has_parent] or list(nodes.keys())[:1]
    roots_set = set(roots)
    all_parents = {nid: [] for nid in nodes}
    for f, t in tree_edges:
        if f in nodes and t in nodes: all_parents[t].append(f)
    parent_of = {}
    for nid, plist in all_parents.items():
        if not plist: continue
        root_parents = [p for p in plist if p in roots_set]
        parent_of[nid] = root_parents[0] if root_parents else plist[0]
    children_of_single = {n: [] for n in nodes}
    for t, f in parent_of.items(): children_of_single[f].append(t)
    margin_x, spine_y = 120, 400
    v_spacing, h_spacing = 110, 30
    incline_dx = v_spacing / math.tan(math.radians(60))
    subtree_w = {}
    def get_sw(nid):
        ch = children_of_single.get(nid, [])
        if not ch: subtree_w[nid] = node_widths[nid]
        else: subtree_w[nid] = max(node_widths[nid], sum(get_sw(c) for c in ch) + max(0, len(ch)-1)*h_spacing)
        return subtree_w[nid]
    for nid in nodes:
        if nid not in subtree_w: get_sw(nid)
    positions, order, root_spine_x = {}, [], {}
    spine_spacing = 100; spine_start_x = margin_x + 100; root_x = spine_start_x
    def place_subtree(nid, cx, cy, side, depth):
        positions[nid] = (cx, cy)
        if nid not in order: order.append(nid)
        ch = children_of_single.get(nid, [])
        if not ch: return
        total_w = sum(subtree_w.get(c, node_widths[c]) for c in ch) + max(0, len(ch)-1)*h_spacing
        start_x = cx - total_w / 2
        for child in ch:
            cw = subtree_w.get(child, node_widths[child])
            child_cx = start_x + cw / 2 + incline_dx
            child_cy = cy + side * v_spacing
            place_subtree(child, child_cx, child_cy, side, depth + 1)
            start_x += cw + h_spacing
    for root in roots:
        rw = subtree_w[root]; sx = root_x + rw / 2
        root_spine_x[root] = sx; positions[root] = (sx, spine_y); order.append(root)
        ch = children_of_single.get(root, [])
        above = [c for i, c in enumerate(ch) if i % 2 == 0]
        below = [c for i, c in enumerate(ch) if i % 2 == 1]
        for group, side in [(above, -1), (below, 1)]:
            if not group: continue
            total_w = sum(subtree_w.get(c, node_widths[c]) for c in group) + max(0, len(group)-1)*h_spacing
            start_x = sx - total_w / 2
            for child in group:
                cw = subtree_w.get(child, node_widths[child])
                child_cx = start_x + cw / 2 + incline_dx
                child_cy = spine_y + side * v_spacing
                place_subtree(child, child_cx, child_cy, side, 1)
                start_x += cw + h_spacing
        root_x += rw + spine_spacing
    for nid in nodes:
        if nid not in positions: positions[nid] = (margin_x, spine_y + 250); order.append(nid)
    if positions:
        min_x = min(x - node_widths[n]/2 for n,(x,y) in positions.items())
        max_x = max(x + node_widths[n]/2 for n,(x,y) in positions.items())
        min_y = min(y - bh/2 for n,(x,y) in positions.items())
        max_y = max(y + bh/2 for n,(x,y) in positions.items())
        W = int(max_x - min_x + 2*margin_x); H = int(max_y - min_y + 2*margin_x)
        sx, sy = margin_x - min_x, margin_x - min_y
        positions = {n: (x+sx, y+sy) for n,(x,y) in positions.items()}
        spine_y += sy; root_spine_x = {r: x+sx for r,x in root_spine_x.items()}; spine_start_x += sx
    else: W, H = 600, 400
    return positions, order, W, H, spine_y, roots, root_spine_x, spine_start_x, parent_of


def _curvy_path(fx, fy, tx, ty):
    mx, my = (fx + tx) / 2, (fy + ty) / 2
    dx, dy = tx - fx, ty - fy
    d = math.hypot(dx, dy) or 1
    ox, oy = dy / d * 80, -dx / d * 80
    cx, cy = mx + ox, my + oy
    return f"M{fx:.1f},{fy:.1f} Q{cx:.1f},{cy:.1f} {tx:.1f},{ty:.1f}"


def _make_connections(nodes, tree_edges, free_edges):
    c = {nid: [] for nid in nodes}
    for f, t in tree_edges: c.setdefault(f, []).append(t); c.setdefault(t, []).append(f)
    for f, t in free_edges: c.setdefault(f, []).append(t); c.setdefault(t, []).append(f)
    for nid in c: c[nid] = list(set(c[nid]))
    return c


def _make_nodes_html(nodes, order, positions, nw_dict, bh, focus, annotations=None):
    hh = bh / 2; r = []
    for nid in order:
        if nid not in positions: continue
        x, y = positions[nid]; nw = nw_dict[nid]; left = x - nw / 2; top = y - hh
        is_focus = focus is not None and nid == focus; cls = 'node focus' if is_focus else 'node'
        le = nodes[nid].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        ann = annotations.get(nid, '') if annotations else ''
        title_attr = f' title="{ann}"' if ann else ''
        r.append(f'<div class="{cls}" data-id="{nid}"{title_attr} style="left:{left:.1f}px;top:{top:.1f}px;width:{nw:.0f}px;height:{bh}px;">{le}</div>')
    return r


def generate_fishbone_html(nodes, tree_edges, free_edges, output_path, focus=None, title=None, annotations=None):
    t = THEME
    node_widths = compute_node_widths(nodes, min_w=140, char_w=8, pad=36)
    bh = 42; hh = bh / 2
    positions, order, W, H, spine_y, roots, root_spine_x, spine_start_x, parent_of = _fishbone_layout(nodes, tree_edges, node_widths, bh)
    connections = _make_connections(nodes, tree_edges, free_edges)
    svg = []; lc = t['timeline_line']; dc = t['timeline_dot']; dfc = t['timeline_dot_focus']
    # Spine line with symmetric extension
    spine_line_start = max(spine_start_x - 20, 80)
    first_root = min(root_spine_x, key=lambda r: root_spine_x[r]) if root_spine_x else None
    first_root_left = root_spine_x[first_root] - node_widths[first_root] / 2 if first_root else 0
    length1 = first_root_left - spine_line_start
    rightmost_edge = max(x + node_widths[n] / 2 for n, (x, y) in positions.items()) if positions else 0
    spine_arrow_x = rightmost_edge + length1
    svg.append(f'<line x1="{spine_line_start:.1f}" y1="{spine_y}" x2="{spine_arrow_x:.1f}" y2="{spine_y}" stroke="{lc}" stroke-width="3" stroke-linecap="round" />')
    svg.append(f'<polygon points="{spine_arrow_x:.1f},{spine_y} {spine_arrow_x-12:.1f},{spine_y-6:.1f} {spine_arrow_x-12:.1f},{spine_y+6:.1f}" fill="{lc}" />')
    # Title box — left upper corner
    title_text = title or 'fishbone'
    tw = len(title_text) * 8 + 30; hx = 40; hy = 20
    svg.append(f'<rect x="{hx:.1f}" y="{hy:.1f}" width="{tw:.0f}" height="{bh:.0f}" rx="6" ry="6" fill="{t["focus_fill"]}" stroke="{t["focus_border"]}" stroke-width="2" />')
    svg.append(f'<text x="{hx+tw/2:.1f}" y="{hy+bh/2+1:.1f}" text-anchor="middle" dominant-baseline="central" font-family="{t["font"]}" font-size="{t["font_size"]}px" fill="{t["focus_text"]}" font-weight="600">{title_text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")}</text>')
    # Bones and connectors
    for nid in order:
        if nid not in positions: continue
        cx, cy = positions[nid]; is_focus = focus is not None and nid == focus
        if nid in root_spine_x:
            sx = root_spine_x[nid]
            svg.append(f'<circle cx="{sx:.1f}" cy="{spine_y}" r="6" fill="{dfc if is_focus else dc}" />')
        elif nid in parent_of:
            pid = parent_of[nid]
            if pid in positions:
                px, py = positions[pid]
                if pid in root_spine_x:
                    sx = root_spine_x[pid]
                    svg.append(f'<line x1="{sx:.1f}" y1="{spine_y}" x2="{cx:.1f}" y2="{cy:.1f}" stroke="{lc}" stroke-width="2" />')
                else:
                    svg.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{cx:.1f}" y2="{cy:.1f}" stroke="{t["arrow"]}" stroke-width="1.5" />')
    # Cross-branch edges as curvy green dashed lines
    structural_edges = set()
    for child, par in parent_of.items(): structural_edges.add((par, child))
    for fi, ti in tree_edges:
        if (fi, ti) not in structural_edges and fi in positions and ti in positions:
            fx, fy = positions[fi]; tx, ty = positions[ti]
            svg.append(f'<path class="arrow-line" data-from="{fi}" data-to="{ti}" data-width="1.5" d="{_curvy_path(fx, fy, tx, ty)}" stroke="{t["free_arrow"]}" stroke-width="1.5" fill="none" stroke-dasharray="6,4" marker-end="url(#free-arrowhead)" />')
    # Free edges as curvy green dashed lines
    for fi, ti in free_edges:
        if fi in positions and ti in positions:
            fx, fy = positions[fi]; tx, ty = positions[ti]
            svg.append(f'<path class="arrow-line" data-from="{fi}" data-to="{ti}" data-width="1.5" d="{_curvy_path(fx, fy, tx, ty)}" stroke="{t["free_arrow"]}" stroke-width="1.5" fill="none" stroke-dasharray="6,4" marker-end="url(#free-arrowhead)" />')
    nodes_html = _make_nodes_html(nodes, order, positions, node_widths, bh, focus, annotations)
    # Dot grid as SVG pattern (html2canvas-compatible)
    dotgrid = f'<defs><pattern id="dotgrid" x="0" y="0" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r="1" fill="{t["grid_minor"]}"/></pattern></defs><rect width="{W}" height="{H}" fill="url(#dotgrid)" />'
    html = _html_template(t, W, H, svg, nodes_html, connections, dotgrid, output_path)
    with open(output_path, 'w', encoding='utf-8') as f: f.write(html)
    print(f"HTML saved to: {output_path}"); return output_path


def _html_template(t, W, H, svg, nodes_html, connections, dotgrid, output_path):
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Fishbone Diagram</title><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet"><style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:{t['bg']};font-family:{t['font']};overflow:auto;min-width:fit-content;padding:20px}}.diagram-container{{position:relative;width:{W}px;height:{H}px;flex-shrink:0}}.node{{position:absolute;text-align:center;display:flex;align-items:center;justify-content:center;border:{t['node_border_w']}px solid {t['node_border']};background:{t['node_fill']};border-radius:{t['border_radius']}px;font-size:{t['font_size']}px;color:{t['text']};padding:4px 10px;box-shadow:2px 2px 6px {t['node_shadow']};cursor:default;transition:box-shadow .2s,transform .15s,opacity .2s;z-index:2;line-height:1.3;user-select:none}}.node:hover{{box-shadow:3px 3px 12px {t['node_shadow_hover']};transform:translateY(-1px);z-index:10}}.node.focus{{background:{t['focus_fill']};border-color:{t['focus_border']};border-width:{t['focus_border_w']}px;color:{t['focus_text']};font-weight:600}}.node.focus::before{{content:'\\2605 ';color:{t['star_color']}}}.arrows-svg{{position:absolute;top:0;left:0;width:100%;height:100%;z-index:1;pointer-events:none}}.arrow-line{{transition:opacity .2s,stroke-width .2s}}.toolbar{{position:fixed;top:16px;right:16px;display:flex;gap:8px;z-index:100}}.toolbar button{{padding:8px 16px;border:1px solid {t['node_border']};border-radius:6px;background:{t['node_fill']};color:{t['text']};font-family:{t['font']};font-size:13px;cursor:pointer;box-shadow:1px 1px 4px {t['node_shadow']};transition:background .2s,transform .1s}}.toolbar button:hover{{background:{t['focus_fill']};transform:translateY(-1px)}}.toolbar button:active{{transform:translateY(0)}}.toolbar button:disabled{{opacity:.5;cursor:not-allowed}}</style></head><body><div class="toolbar"><button id="btn-copy" onclick="copyToClipboard()">&#128203; Copy Image</button><button id="btn-download" onclick="downloadPNG()">&#11015; Download PNG</button></div><div class="diagram-container"><svg class="arrows-svg" xmlns="http://www.w3.org/2000/svg"><defs><marker id="arrowhead" markerWidth="12" markerHeight="8" refX="0" refY="4" orient="auto" markerUnits="userSpaceOnUse"><polygon points="0 0,12 4,0 8" fill="{t['arrow']}"/></marker><marker id="free-arrowhead" markerWidth="12" markerHeight="8" refX="0" refY="4" orient="auto" markerUnits="userSpaceOnUse"><polygon points="0 0,12 4,0 8" fill="{t['free_arrow']}"/></marker></defs>{dotgrid}{chr(10).join(svg)}</svg>{chr(10).join(nodes_html)}</div><script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script><script>const connections={json.dumps(connections)};document.querySelectorAll('.node').forEach(node=>{{node.addEventListener('mouseenter',()=>{{const id=node.dataset.id;const connected=new Set(connections[id]||[]);connected.add(id);document.querySelectorAll('.node').forEach(n=>{{if(!connected.has(n.dataset.id))n.style.opacity='0.25'}});document.querySelectorAll('.arrow-line').forEach(line=>{{const from=line.dataset.from,to=line.dataset.to;if(from!==id&&to!==id)line.style.opacity='0.15';else line.style.strokeWidth='3'}})}});node.addEventListener('mouseleave',()=>{{document.querySelectorAll('.node').forEach(n=>n.style.opacity='1');document.querySelectorAll('.arrow-line').forEach(line=>{{line.style.strokeWidth=line.dataset.width;line.style.opacity='1'}})}})}});async function captureDiagram(){{const container=document.querySelector('.diagram-container');document.querySelectorAll('.node').forEach(n=>n.style.opacity='1');document.querySelectorAll('.arrow-line').forEach(l=>{{l.style.strokeWidth=l.dataset.width;l.style.opacity='1'}});return await html2canvas(container,{{backgroundColor:'{t["bg"]}',scale:2,useCORS:true,logging:false}})}}async function copyToClipboard(){{const btn=document.getElementById('btn-copy');btn.disabled=true;btn.textContent='Copying...';try{{const canvas=await captureDiagram();canvas.toBlob(async(blob)=>{{try{{await navigator.clipboard.write([new ClipboardItem({{'image/png':blob}})]);btn.textContent='✓ Copied!'}}catch(e){{window.open(URL.createObjectURL(blob),'_blank');btn.textContent='Opened in tab'}}setTimeout(()=>{{btn.textContent='📋 Copy Image';btn.disabled=false}},2000)}})}}catch(e){{console.error(e);btn.textContent='✗ Failed';setTimeout(()=>{{btn.textContent='📋 Copy Image';btn.disabled=false}},2000)}}}}async function downloadPNG(){{const btn=document.getElementById('btn-download');btn.disabled=true;btn.textContent='Rendering...';try{{const canvas=await captureDiagram();const link=document.createElement('a');link.download='{os.path.splitext(os.path.basename(output_path))[0]}.png';link.href=canvas.toDataURL('image/png');link.click();btn.textContent='✓ Downloaded!'}}catch(e){{console.error(e);btn.textContent='✗ Failed'}}setTimeout(()=>{{btn.textContent='⬇ Download PNG';btn.disabled=false}},2000)}}</script></body></html>"""


def main():
    parser = argparse.ArgumentParser(description='Render graphai-dsl DSL to fishbone HTML')
    parser.add_argument('input', help='DSL file path, or inline DSL text with --dsl')
    parser.add_argument('output', nargs='?', default=None, help='Output HTML path')
    parser.add_argument('--dsl', action='store_true', help='Treat input as inline DSL text')
    args = parser.parse_args()
    if args.dsl:
        dsl_text = args.input; out = args.output or 'diagram_output.html'
    else:
        with open(args.input, 'r', encoding='utf-8') as f: dsl_text = f.read()
        out = args.output or os.path.join(os.getcwd(), os.path.splitext(os.path.basename(args.input))[0] + '.html')
    nodes, te, fe, focus, dsl_style, dsl_title, annotations, sides = parse_dsl(dsl_text)
    generate_fishbone_html(nodes, te, fe, out, focus=focus, title=dsl_title)


if __name__ == '__main__':
    main()
