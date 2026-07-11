#!/usr/bin/env python3
"""Diagram renderer — school sheet / hand-drawn style. Outputs PNG via Pillow.

Direct rays (straight lines) with gentle pencil shakiness.
Free connectors (-->): dashed lines, different color.
Per-node box widths sized to label length.
"""

import sys, os, re, random, math
from PIL import Image, ImageDraw, ImageFont

# ---------- DSL Parser ----------

def _parse_annotation(line):
    """Extract annotation from | "text" anywhere in the line. Returns (remaining_line, annotation_or_None)."""
    m = re.search(r'\|\s*"([^"]+)"', line)
    if m:
        remaining = (line[:m.start()] + line[m.end():]).strip()
        remaining = re.sub(r'\s+', ' ', remaining)
        return remaining, m.group(1)
    return line, None

def parse_dsl(text):
    nodes, tree_edges, free_edges, focus = {}, [], [], None
    annotations = {}
    sides = {}  # node_id -> 'Left' or 'Right' (for mindmap style)
    style = None
    title = None
    last_id = None
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Check for format directive: format=1
        m_fmt = re.match(r'^format\s*=\s*"?(\w+)"?\s*$', line, re.IGNORECASE)
        if m_fmt:
            continue  # format version, ignored for compatibility
        # Check for style directive: style=ancient or style="notebook"
        m_style = re.match(r'^style\s*=\s*"?(\w+)"?\s*$', line, re.IGNORECASE)
        if m_style:
            style = m_style.group(1).lower()
            continue
        # Check for title directive: title="My Diagram" or title=My Diagram
        m_title = re.match(r'^title\s*=\s*"([^"]+)"\s*$', line)
        if m_title:
            title = m_title.group(1)
            continue
        m_title2 = re.match(r'^title\s*=\s*(.+)$', line)
        if m_title2:
            title = m_title2.group(1).strip()
            continue
        # Strip focus marker (*) before matching
        is_focus = line.startswith('*')
        if is_focus:
            line = line[1:].strip()
        # Extract annotation: | "tooltip text"
        line, annotation = _parse_annotation(line)
        if annotation is not None:
            # Annotation will be assigned to the node ID on this line
            pass
        # Extract side tag: [Left] or [Right]
        side = None
        m_side = re.search(r'\[(Left|Right)\]', line, re.IGNORECASE)
        if m_side:
            side = m_side.group(1).capitalize()
            line = line[:m_side.start()] + line[m_side.end():]
            line = line.strip()
            # Collapse multiple spaces
            line = re.sub(r'\s+', ' ', line)

        m_free_lab = re.match(r'^(\w+)\s+"([^"]+)"\s*-->\s*(.+)$', line)
        m_free_id  = re.match(r'^(\w+)\s*-->\s*(.+)$', line)
        m_free_bare= re.match(r'^-->\s*(.+)$', line)
        m_tree     = re.match(r'^(\w+)\s+"([^"]+)"\s*(?:->\s*(.+))?$', line)
        if m_free_lab:
            nid, label, deps = m_free_lab.group(1), m_free_lab.group(2), m_free_lab.group(3)
            nodes[nid] = label; last_id = nid
            if is_focus: focus = nid
            if annotation: annotations[nid] = annotation
            if side: sides[nid] = side
            for d in deps.split(','):
                d = d.strip().lstrip('*')  # Strip focus marker from child IDs
                if d: free_edges.append((nid, d))
        elif m_free_id:
            nid, deps = m_free_id.group(1), m_free_id.group(2)
            if nid not in nodes: nodes[nid] = nid
            last_id = nid
            if is_focus: focus = nid
            if annotation: annotations[nid] = annotation
            if side: sides[nid] = side
            for d in deps.split(','):
                d = d.strip().lstrip('*')  # Strip focus marker from child IDs
                if d: free_edges.append((nid, d))
        elif m_free_bare:
            if last_id is None: continue
            for d in m_free_bare.group(1).split(','):
                d = d.strip().lstrip('*')  # Strip focus marker from child IDs
                if d: free_edges.append((last_id, d))
        elif m_tree:
            nid, label, deps = m_tree.group(1), m_tree.group(2), m_tree.group(3)
            nodes[nid] = label; last_id = nid
            if is_focus: focus = nid
            if annotation: annotations[nid] = annotation
            if side: sides[nid] = side
            if deps:
                for d in deps.split(','):
                    d = d.strip().lstrip('*')  # Strip focus marker from child IDs
                    if d: tree_edges.append((nid, d))
        else:
            # Bare ID (no label, no edges) — still store annotation
            m_bare = re.match(r'^(\w+)$', line)
            if m_bare:
                nid = m_bare.group(1)
                if nid not in nodes: nodes[nid] = nid
                last_id = nid
                if annotation: annotations[nid] = annotation
    for _, d in tree_edges + free_edges:
        if d not in nodes: nodes[d] = d
    return nodes, tree_edges, free_edges, focus, style, title, annotations, sides

# ---------- Layout ----------

def compute_layers(nodes, tree_edges):
    """BFS from roots — roots at top, foundations at bottom.
    Arrow semantics: A -> B means A depends on B (A needs B).
    Roots = nodes that nothing depends on (nobody points to them with ->).
    These are the top-level / most dependent items.
    """
    deps_of = {nid: set() for nid in nodes}
    dependents_of = {nid: set() for nid in nodes}
    for f, t in tree_edges:
        deps_of[f].add(t)
        dependents_of[t].add(f)

    # Roots = nodes that nothing depends on (top-level items)
    roots = [n for n in nodes if not dependents_of[n]]
    if not roots:
        roots = list(nodes.keys())[:1]

    # BFS from roots: roots = layer 0, their dependencies = layer 1, etc.
    layers, visited = {}, set()
    from collections import deque
    q = deque([(n, 0) for n in roots])
    while q:
        nid, lv = q.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        layers[nid] = max(lv, layers.get(nid, -1))
        for d in sorted(deps_of[nid]):
            if d not in visited:
                q.append((d, lv + 1))

    # Any unreferenced nodes
    ml = max(layers.values()) if layers else 0
    for n in nodes:
        if n not in layers:
            ml += 1
            layers[n] = ml

    return layers


def compute_node_widths(nodes, min_w=140, char_w=9, pad=40):
    """Compute per-node box widths based on label length."""
    return {nid: max(min_w, len(label) * char_w + pad) for nid, label in nodes.items()}


def layout_nodes(nodes, tree_edges, width, height, node_widths=None):
    """Layout with per-node widths using subtree-based positioning.
    Computes subtree widths bottom-up, then positions top-down
    to keep children close to parents and minimize crossed arrows.
    Returns positions, layers, node_widths, box_h, v_gap."""
    from collections import Counter as _Counter

    layers = compute_layers(nodes, tree_edges)
    bh = 42; h_gap = 30; v_gap = 112; y_pad = 60

    if node_widths is None:
        node_widths = compute_node_widths(nodes)

    # Build parent-child relationships (tree edges only, adjacent layers)
    children_of = {n: [] for n in nodes}
    parent_of = {n: None for n in nodes}
    for f, t in tree_edges:
        if layers.get(t, -1) == layers.get(f, -1) + 1:
            children_of[f].append(t)
            if parent_of[t] is None:
                parent_of[t] = f
    for n in children_of:
        children_of[n] = sorted(children_of[n])

    # Find roots (no parent in tree)
    roots = [n for n in nodes if parent_of[n] is None]
    if not roots:
        roots = list(nodes.keys())[:1]

    # Group by layer
    layer_groups = {}
    for nid, lv in layers.items():
        layer_groups.setdefault(lv, []).append(nid)

    max_lv = max(layers.values()) if layers else 0

    # Step 1: Compute subtree widths bottom-up
    # subtree_width[n] = width needed to lay out n and all its descendants
    subtree_width = {}

    def compute_subtree_width(nid):
        children = children_of.get(nid, [])
        if not children:
            subtree_width[nid] = node_widths[nid]
        else:
            children_total = sum(compute_subtree_width(c) for c in children)
            children_total += max(0, len(children) - 1) * h_gap
            subtree_width[nid] = max(node_widths[nid], children_total)
        return subtree_width[nid]

    for nid in nodes:
        if nid not in subtree_width:
            compute_subtree_width(nid)

    # Step 2: Position nodes top-down, keeping subtrees together
    positions = {}

    def position_subtree(nid, left_x, y):
        """Position nid and its descendants. left_x is the left edge of allocated space."""
        children = children_of.get(nid, [])
        stw = subtree_width[nid]
        # Center this node within its subtree width
        node_x = left_x + stw / 2
        positions[nid] = (node_x, y)

        if children:
            # Total width of children subtrees
            children_total = sum(subtree_width[c] for c in children)
            children_total += max(0, len(children) - 1) * h_gap
            # Start children centered under parent
            cx = left_x + (stw - children_total) / 2
            child_y = y + v_gap
            for c in children:
                position_subtree(c, cx, child_y)
                cx += subtree_width[c] + h_gap

    # Position each root's subtree
    roots_total = sum(subtree_width[r] for r in roots)
    roots_total += max(0, len(roots) - 1) * h_gap

    # Ensure enough horizontal space
    min_width = max(600, roots_total + h_gap * 2)
    if min_width > width:
        width = min_width

    rx = (width - roots_total) / 2
    for r in roots:
        position_subtree(r, rx, y_pad)
        rx += subtree_width[r] + h_gap

    # Handle nodes not reached by tree traversal (orphaned by layer mismatch)
    for nid in nodes:
        if nid not in positions:
            lv = layers[nid]
            y = y_pad + lv * v_gap
            # Place at center, will be resolved by overlap fix
            positions[nid] = (width / 2, y)

    # Step 3: Resolve any remaining overlaps per layer
    for _ in range(20):
        changed = False
        for lv in range(max_lv + 1):
            nlist = sorted(layer_groups.get(lv, []), key=lambda n: positions[n][0])
            for i in range(1, len(nlist)):
                prev = nlist[i - 1]
                curr = nlist[i]
                prev_right = positions[prev][0] + node_widths[prev] / 2
                curr_left = positions[curr][0] - node_widths[curr] / 2
                if curr_left < prev_right + h_gap:
                    shift = prev_right + h_gap - curr_left
                    # Shift the entire subtree of curr
                    def shift_subtree(nid, dx):
                        positions[nid] = (positions[nid][0] + dx, positions[nid][1])
                        for c in children_of.get(nid, []):
                            shift_subtree(c, dx)
                    shift_subtree(curr, shift)
                    changed = True
        if not changed:
            break

    # Step 4: Center the whole diagram
    if positions:
        min_x = min(x - node_widths[n] / 2 for n, (x, y) in positions.items())
        max_x = max(x + node_widths[n] / 2 for n, (x, y) in positions.items())
        content_w = max_x - min_x
        shift = (width - content_w) / 2 - min_x
        positions = {n: (x + shift, y) for n, (x, y) in positions.items()}

    return positions, layers, node_widths, bh, v_gap

# ---------- Drawing ----------

_rng = random.Random(42)

def _shake(v, a=1.5): return v + _rng.uniform(-a, a)

def _pencil_ray(draw, x1, y1, x2, y2, fill, width=2):
    """Straight ray with gentle pencil wobble — like a ruler-drawn line."""
    dist = math.hypot(x2-x1, y2-y1)
    segs = max(2, int(dist / 30))
    pts = [(x1, y1)]
    for i in range(1, segs):
        t = i / segs
        px = x1 + (x2-x1)*t + _rng.uniform(-0.7, 0.7)
        py = y1 + (y2-y1)*t + _rng.uniform(-0.7, 0.7)
        pts.append((px, py))
    pts.append((x2, y2))
    for i in range(len(pts)-1):
        draw.line([pts[i], pts[i+1]], fill=fill, width=width, joint='curve')

def _arrowhead(draw, x2, y2, angle, fill, size=14):
    a1, a2 = angle + math.radians(150), angle - math.radians(150)
    pts = [(_shake(x2, .4), _shake(y2, .4)),
           (_shake(x2 + size*math.cos(a1), .4), _shake(y2 + size*math.sin(a1), .4)),
           (_shake(x2 + size*math.cos(a2), .4), _shake(y2 + size*math.sin(a2), .4))]
    draw.polygon(pts, fill=fill)

def _pencil_arrow(draw, x1, y1, x2, y2, fill, lw=2, hs=14):
    dist = math.hypot(x2-x1, y2-y1)
    shorten = hs * 0.6
    if dist > shorten * 2:
        r = (dist - shorten) / dist
        lx, ly = x1 + (x2-x1)*r, y1 + (y2-y1)*r
    else:
        lx, ly = x1, y1
    _pencil_ray(draw, x1, y1, lx, ly, fill=fill, width=lw)
    _arrowhead(draw, x2, y2, math.atan2(y2-y1, x2-x1), fill=fill, size=hs)

def _dashed_ray(draw, x1, y1, x2, y2, fill, width=2, dash=10, gap=7):
    dist = math.hypot(x2-x1, y2-y1)
    if dist < 1: return
    dx, dy = (x2-x1)/dist, (y2-y1)/dist
    pos, on = 0, True
    while pos < dist:
        seg = dash if on else gap
        ep = min(pos + seg, dist)
        if on:
            sx, sy = x1+dx*pos, y1+dy*pos
            ex, ey = x1+dx*ep, y1+dy*ep
            _pencil_ray(draw, sx, sy, ex, ey, fill=fill, width=width)
        pos = ep; on = not on

def _dashed_arrow(draw, x1, y1, x2, y2, fill, lw=2, hs=11, dash=10, gap=7):
    dist = math.hypot(x2-x1, y2-y1)
    shorten = hs * 0.6
    if dist > shorten * 2:
        r = (dist - shorten) / dist
        lx, ly = x1 + (x2-x1)*r, y1 + (y2-y1)*r
    else:
        lx, ly = x1, y1
    _dashed_ray(draw, x1, y1, lx, ly, fill=fill, width=lw, dash=dash, gap=gap)
    _arrowhead(draw, x2, y2, math.atan2(y2-y1, x2-x1), fill=fill, size=hs)

def _shaky_rect(draw, x, y, w, h, fill, outline, ow=2, radius=0):
    if radius > 0:
        # Rounded rectangle: slight shake on position, clean rounded corners
        sx, sy = _shake(x, 0.8), _shake(y, 0.8)
        draw.rounded_rectangle([sx, sy, sx + w, sy + h], radius=radius, fill=fill, outline=outline, width=ow)
    else:
        c = [(_shake(x,1.2),_shake(y,1.2)),(_shake(x+w,1.2),_shake(y,1.2)),
             (_shake(x+w,1.2),_shake(y+h,1.2)),(_shake(x,1.2),_shake(y+h,1.2))]
        pts = []
        for i in range(4):
            x1,y1 = c[i]; x2,y2 = c[(i+1)%4]
            for t in [.33,.66]:
                pts.append((x1+(x2-x1)*t+_rng.uniform(-1,1), y1+(y2-y1)*t+_rng.uniform(-1,1)))
            pts.append((x2, y2))
        draw.polygon(pts, fill=fill)
        for i in range(4):
            x1,y1 = c[i]; x2,y2 = c[(i+1)%4]
            _pencil_ray(draw, x1, y1, x2, y2, fill=outline, width=ow)

def _font(names, sz):
    for n in names:
        try: return ImageFont.truetype(n, sz)
        except: pass
    return ImageFont.load_default()

FONTS = ['comic.ttf','comicbd.ttf','COMICUN.TTF',
         'C:/Windows/Fonts/comic.ttf','C:/Windows/Fonts/comicbd.ttf',
         'C:/Windows/Fonts/COMICUN.TTF','segoepr.ttf','C:/Windows/Fonts/segoepr.ttf']

def _box_exit(cx, cy, hw, hh, tx, ty, margin=6, prefer_vertical=False):
    """Find the point on the box border closest to target (tx,ty),
    going from center (cx,cy) toward (tx,ty).
    If prefer_vertical=True, force exit from bottom/top edge."""
    dx, dy = tx - cx, ty - cy
    dist = math.hypot(dx, dy)
    if dist < 0.001:
        return cx, cy - hh - margin  # straight up
    if prefer_vertical:
        # Exit from bottom (going down) or top (going up)
        if dy >= 0:
            return cx, cy + hh + margin
        else:
            return cx, cy - hh - margin
    # Which edge does the ray hit?
    cos_a, sin_a = dx / dist, dy / dist
    if abs(cos_a) > 0.001:
        t_x = (hw + margin) / abs(cos_a)
    else:
        t_x = 99999
    if abs(sin_a) > 0.001:
        t_y = (hh + margin) / abs(sin_a)
    else:
        t_y = 99999
    t = min(t_x, t_y)
    return cx + t * cos_a, cy + t * sin_a

def _draw_bg_notebook(d, W, H, S, img):
    """School notebook background: graph paper, red margin, holes."""
    for x in range(0, W*S+1, 10*S): d.line([(x,0),(x,H*S)], fill='#eae8e2', width=1)
    for y in range(0, H*S+1, 10*S): d.line([(0,y),(W*S,y)], fill='#eae8e2', width=1)
    for x in range(0, W*S+1, 50*S): d.line([(x,0),(x,H*S)], fill='#d2d0ca', width=max(1,S))
    for y in range(0, H*S+1, 50*S): d.line([(0,y),(W*S,y)], fill='#d2d0ca', width=max(1,S))
    d.line([(30*S,0),(30*S,H*S)], fill='#d06060', width=max(1,S))
    for fy in [.2,.5,.8]:
        cy=int(H*S*fy); cx=15*S; r=6*S
        d.ellipse([(cx-r,cy-r),(cx+r,cy+r)], outline='#c0c0c0', width=max(1,S))


PARCHMENT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'parchment.jpg')


def _draw_bg_ancient(d, W, H, S, img):
    """Ancient parchment background: real parchment texture with faint ruling and ornate border."""
    if os.path.exists(PARCHMENT_PATH):
        try:
            bg = Image.open(PARCHMENT_PATH).convert('RGB')
            bg = bg.resize((W * S, H * S), Image.LANCZOS)
            img.paste(bg, (0, 0))
        except Exception:
            pass


def _draw_bg_blueprint(d, W, H, S, img):
    """Blueprint background: dark blue with white grid lines and border frame."""
    # Major grid
    for x in range(0, W*S+1, 50*S):
        d.line([(x, 0), (x, H*S)], fill='#1a4a7a', width=max(1, S))
    for y in range(0, H*S+1, 50*S):
        d.line([(0, y), (W*S, y)], fill='#1a4a7a', width=max(1, S))
    # Minor grid
    for x in range(0, W*S+1, 10*S):
        d.line([(x, 0), (x, H*S)], fill='#153d65', width=1)
    for y in range(0, H*S+1, 10*S):
        d.line([(0, y), (W*S, y)], fill='#153d65', width=1)
    # Border frame
    m = 12 * S
    d.rectangle([(m, m), (W*S - m, H*S - m)], outline='#4a90d9', width=max(2, 2*S))


STYLES = {
    'notebook': {
        'bg': '#faf8f0',
        'node_fill': '#fffff8',
        'node_outline': '#2a2a2a',
        'node_outline_w': 2,
        'focus_fill': '#fffde0',
        'focus_outline': '#1a5276',
        'focus_outline_w': 3,
        'focus_text': '#1a5276',
        'text': '#1a1a1a',
        'arrow': '#2a2a2a',
        'free_arrow': '#8b4513',
        'title': '#4a4a4a',
        'title_text': 'dependency graph',
        'draw_bg': _draw_bg_notebook,
    },
    'ancient': {
        'bg': '#f0e4c8',
        'node_fill': '#f5ecd4',
        'node_outline': '#5c3a1e',
        'node_outline_w': 2,
        'focus_fill': '#e8d498',
        'focus_outline': '#6b3a10',
        'focus_outline_w': 3,
        'focus_text': '#6b3a10',
        'text': '#2c1a0a',
        'arrow': '#3e2510',
        'free_arrow': '#7a5c30',
        'title': '#7a6040',
        'title_text': 'lineage',
        'draw_bg': _draw_bg_ancient,
    },
    'blueprint': {
        'bg': '#0d2b4a',
        'node_fill': '#14375a',
        'node_outline': '#4a90d9',
        'node_outline_w': 2,
        'focus_fill': '#1a5276',
        'focus_outline': '#7ec8e3',
        'focus_outline_w': 3,
        'focus_text': '#7ec8e3',
        'text': '#c8e0f4',
        'arrow': '#4a90d9',
        'free_arrow': '#7ec8e3',
        'title': '#4a90d9',
        'title_text': 'blueprint',
        'draw_bg': _draw_bg_blueprint,
        'corner_radius': 8,
    },
}


def render_diagram(nodes, tree_edges, free_edges, output_path, focus=None, style='notebook', title=None):
    st = STYLES.get(style, STYLES['notebook'])
    bh = 42; S = 2  # base scale

    # Compute per-node widths based on label length
    node_widths = compute_node_widths(nodes)

    # Estimate canvas size
    avg_w = sum(node_widths.values()) / len(node_widths) if node_widths else 200
    tw = max(1000, len(nodes) * int(avg_w + 20)); th = 1400
    positions, layers, node_widths, bh, vg = layout_nodes(nodes, tree_edges, tw, th, node_widths=node_widths)
    hh = bh / 2

    margin = 60  # margin in logical coords
    if positions:
        # Compute bounding box of all nodes
        min_x = min(x - node_widths[n]/2 for n, (x, y) in positions.items())
        max_x = max(x + node_widths[n]/2 for n, (x, y) in positions.items())
        min_y = min(y - hh for n, (x, y) in positions.items())
        max_y = max(y + hh for n, (x, y) in positions.items())
        content_w = max_x - min_x
        content_h = max_y - min_y
        W = max(600, int(content_w + 2 * margin))
        H = max(400, int(content_h + 2 * margin))
        # Center: shift so content is centered in canvas
        shift_x = margin - min_x + (W - content_w) / 2 - (max_x - min_x) / 2 + content_w / 2 - content_w / 2
        # Simplify: center content in (W x H) canvas
        shift_x = (W - content_w) / 2 - min_x
        shift_y = (H - content_h) / 2 - min_y
        positions = {n: (x + shift_x, y + shift_y) for n, (x, y) in positions.items()}
    else:
        W, H = 600, 400

    # Adaptive scale: ensure nodes are readable
    if node_widths:
        min_node_px = min(node_widths.values()) * S
        target_node_px = 200
        if min_node_px < target_node_px:
            S = max(S, math.ceil(target_node_px / min(node_widths.values())))
    img_w = W * S
    if img_w < 1200:
        S = max(S, math.ceil(1200 / W))
    S = min(S, 4)

    img = Image.new('RGB', (W*S, H*S), st['bg'])
    d = ImageDraw.Draw(img)
    st['draw_bg'](d, W, H, S, img)

    fnt = _font(FONTS, 13*S); tfnt = _font(FONTS, 14*S)

    # Draw nodes with per-node widths
    for nid, label in nodes.items():
        if nid not in positions: continue
        x, y = positions[nid]
        nw = node_widths[nid]
        nhw = nw / 2
        is_focus = (focus is not None and nid == focus)
        fill_color = st['focus_fill'] if is_focus else st['node_fill']
        outline_color = st['focus_outline'] if is_focus else st['node_outline']
        outline_width = max(st['focus_outline_w'], st['focus_outline_w']*S) if is_focus else max(st['node_outline_w'], st['node_outline_w']*S)
        cr = st.get('corner_radius', 0) * S
        _shaky_rect(d, (x-nhw)*S, (y-hh)*S, nw*S, bh*S, fill=fill_color, outline=outline_color, ow=outline_width, radius=cr)
        bb = d.textbbox((0,0), label, font=fnt); tw2=bb[2]-bb[0]; th2=bb[3]-bb[1]
        text_color = st['focus_text'] if is_focus else st['text']
        d.text((x*S-tw2/2, y*S-th2/2-2*S), label, fill=text_color, font=fnt)
        # Star marker for focus node
        if is_focus:
            star_x = x*S - tw2/2 - 14*S
            star_y = (y-hh)*S + 5*S
            d.text((star_x, star_y), '*', fill='#c77d00' if style == 'notebook' else '#8b5a00', font=tfnt)

    # Tree edges — use per-node half-widths, vertical attachment (bottom→top)
    ac = st['arrow']; aw = max(st['node_outline_w'], st['node_outline_w']*S); ahs = 14*S
    for fi, ti in tree_edges:
        if fi not in positions or ti not in positions: continue
        fx, fy = positions[fi]; tx, ty = positions[ti]
        sx, sy = _box_exit(fx, fy, node_widths[fi]/2, hh, tx, ty, prefer_vertical=True)
        ex, ey = _box_exit(tx, ty, node_widths[ti]/2, hh, fx, fy, prefer_vertical=True)
        sx*=S; sy*=S; ex*=S; ey*=S
        _pencil_arrow(d, sx, sy, ex, ey, fill=ac, lw=aw, hs=ahs)

    # Free edges — use per-node half-widths for arrow routing
    fc = st['free_arrow']; fw = max(st['node_outline_w'], st['node_outline_w']*S); fhs = 13*S
    for fi, ti in free_edges:
        if fi not in positions or ti not in positions: continue
        fx, fy = positions[fi]; tx, ty = positions[ti]
        sx, sy = _box_exit(fx, fy, node_widths[fi]/2, hh, tx, ty)
        ex, ey = _box_exit(tx, ty, node_widths[ti]/2, hh, fx, fy)
        sx*=S; sy*=S; ex*=S; ey*=S
        _dashed_arrow(d, sx, sy, ex, ey, fill=fc, lw=fw, hs=fhs, dash=12*S, gap=8*S)

    # Title — DSL title overrides style default
    tt = title or st.get('title_text', '')
    if tt:
        tb = d.textbbox((0,0), tt, font=tfnt); ttw=tb[2]-tb[0]
        d.text((W*S-ttw-20*S, 14*S), tt, fill=st['title'], font=tfnt)

    img.save(output_path, 'PNG')
    print(f"PNG saved to: {output_path}")
    return output_path

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Render graphai-dsl2image DSL to PNG')
    parser.add_argument('input', help='DSL file path, or inline DSL text with --dsl')
    parser.add_argument('output', nargs='?', default=None, help='Output PNG path (default: same name as input)')
    parser.add_argument('--dsl', action='store_true', help='Treat input as inline DSL text')
    parser.add_argument('--style', choices=['notebook', 'ancient', 'blueprint'], default=None,
                        help='Background style: notebook (default), ancient, or blueprint. Overrides DSL style= directive.')
    args = parser.parse_args()

    if args.dsl:
        dsl_text = args.input
        out = args.output or 'diagram_output.png'
    else:
        with open(args.input, 'r', encoding='utf-8') as f: dsl_text = f.read()
        out = args.output or os.path.join(os.getcwd(), os.path.splitext(os.path.basename(args.input))[0] + '.png')

        nodes, te, fe, focus, dsl_style, dsl_title, annotations, sides = parse_dsl(dsl_text)
    # CLI --style overrides DSL style=, DSL style= overrides default
    style = args.style or dsl_style or 'notebook'
    render_diagram(nodes, te, fe, out, focus=focus, style=style, title=dsl_title)

if __name__ == '__main__':
    main()
