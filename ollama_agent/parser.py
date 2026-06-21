"""Parse WRITE/EDIT/FILE/RUN blocks from LLM output."""

import os
import re

_WRITE_SIGNAL_LINE = re.compile(r'\*\*WRITE:\*\*\s*`([^`]+)`|\*\*WRITE:\s*`([^`]+)`\s*\*\*')
_EDIT_SIGNAL_LINE = re.compile(r'\*\*EDIT:\*\*\s*`([^`]+)`|\*\*EDIT:\s*`([^`]+)`\s*\*\*')
_FILE_SIGNAL_LINE = re.compile(r'\*\*FILE:\*\*\s*`([^`]+)`|\*\*FILE:\s*`([^`]+)`\s*\*\*')
_TOOL_SIGNAL_LINE = re.compile(r'\*\*TOOL:\*\*\s*`([^`]+)`|\*\*TOOL:\s*`([^`]+)`\s*\*\*')
_SKILL_SIGNAL_LINE = re.compile(r'\*\*SKILL:\*\*\s*`([^`]+)`|\*\*SKILL:\s*`([^`]+)`\s*\*\*')
_EOF_SIGNAL_LINE = re.compile(
    r'\*\*EOF:\*\*\s*`([^`]+)`'      # **EOF:** `path`
    r'|\*\*EOF:\s*`([^`]+)`\s*\*\*'   # **EOF: `path` **
    r'|\*\*EOF:\*\*\s*([^\s`*]+)'    # **EOF:** path (no backticks)
    r'|\*\*EOF:\s*`([^`]+)`'         # **EOF: `path` (no closing **)
    r'|\*\*EOF:\*\*\s*$'             # **EOF:** (bare, no name — closes current block)
)
_RUN_SIGNAL_LINE = re.compile(r'\*\*RUN:\s*\*\*')
_PATH_SIGNAL = re.compile(r'\*\*(?:WRITE|EDIT|FILE|TOOL|SKILL):\*\*\s*`([^`]+)`|\*\*(?:WRITE|EDIT|FILE|TOOL|SKILL):\s*`([^`]+)`\s*\*\*')
_BASH_BLOCK = re.compile(r'```(?:bash|sh)', re.DOTALL)

_SEARCH_MARKER = '<<<<<<< SEARCH'
_DIVIDER_MARKER = '======='
_REPLACE_MARKER = '>>>>>>> REPLACE'


def _extract_path(match):
    """Extract the file path from a WRITE/EDIT/FILE/EOF regex match.
    Returns empty string for bare EOF markers (no path specified)."""
    for g in match.groups():
        if g is not None and g.strip():
            return g.strip()
    return ""


def _strip_surrounding_fences(raw_code):
    """Remove leading/trailing code fences and trailing EOF/WRITE/EDIT/FILE markers."""
    lines = raw_code.splitlines()
    if not lines:
        return raw_code
    start_idx = 0
    end_idx = len(lines)
    if start_idx < end_idx and re.match(r"^```", lines[start_idx].strip()):
        start_idx += 1
    while end_idx > start_idx and not lines[end_idx - 1].strip():
        end_idx -= 1
    if end_idx > start_idx and lines[end_idx - 1].strip() == "```":
        end_idx -= 1
    while end_idx > start_idx:
        while end_idx > start_idx and not lines[end_idx - 1].strip():
            end_idx -= 1
        if end_idx > start_idx:
            stripped = lines[end_idx - 1].strip()
            if _EOF_SIGNAL_LINE.search(stripped) or _WRITE_SIGNAL_LINE.search(stripped) or _FILE_SIGNAL_LINE.search(stripped) or _EDIT_SIGNAL_LINE.search(stripped):
                end_idx -= 1
            else:
                break
    while end_idx > start_idx and not lines[end_idx - 1].strip():
        end_idx -= 1
    return "\n".join(lines[start_idx:end_idx])


def _parse_params(code):
    """Parse tool/skill parameters from code block.

    Tries JSON first, then falls back to simple key: value format.
    Returns (params_dict, json_error_or_None).
    Handles:
      {"path": "src/app.py", "limit": 10}     -> JSON
      path: src/app.py                          -> {"path": "src/app.py"}
      path: src/app.py                          -> {"path": "src/app.py"}
      limit: 10                                 -> {"limit": 10}
      pattern: "hello.*world"                   -> {"pattern": "hello.*world"}
    """
    import json as _json
    code = code.strip()
    if not code:
        return {}, None
    # Sanitize curly/smart quotes to straight quotes (LLMs sometimes emit these)
    code = code.replace('\u201c', '"').replace('\u201d', '"')
    code = code.replace('\u2018', "'").replace('\u2019', "'")
    # Try JSON first
    looks_like_json = code.startswith('{')
    try:
        result = _json.loads(code)
        if isinstance(result, dict):
            return result, None
    except (ValueError, _json.JSONDecodeError) as e:
        if looks_like_json:
            return {}, str(e)
    # Fallback: parse simple key: value lines
    # Fallback: parse simple key: value lines
    params = {}
    for line in code.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Match key: value (with optional quotes)
        m = re.match(r'^(\w[\w_-]*)\s*[:=]\s*(.+)$', line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            # Strip surrounding quotes
            if (val.startswith('"') and val.endswith('"')) or \
               (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            # Try numeric conversion
            try:
                if '.' in val:
                    val = float(val)
                else:
                    val = int(val)
            except ValueError:
                pass
            # Boolean conversion
            if isinstance(val, str):
                if val.lower() in ('true', 'yes'):
                    val = True
                elif val.lower() in ('false', 'no'):
                    val = False
            params[key] = val
    return params, None


def parse_edit_content(content):
    """Parse search/replace blocks from EDIT block content.
    Returns list of (search_text, replace_text) tuples."""
    blocks = []
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == _SEARCH_MARKER or stripped.startswith('<<<<<<<'):
            search_lines = []
            i += 1
            while i < len(lines) and lines[i].strip() != _DIVIDER_MARKER:
                search_lines.append(lines[i])
                i += 1
            if i >= len(lines):
                break
            i += 1  # skip =======
            replace_lines = []
            while i < len(lines) and lines[i].strip() != _REPLACE_MARKER:
                replace_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # skip >>>>>>> REPLACE
            blocks.append(('\n'.join(search_lines), '\n'.join(replace_lines)))
        else:
            i += 1
    return blocks


def _extract_blocks(text):
    """Low-level block extractor yielding (start, end, path, lang, code, closed, btype)."""
    lines = text.splitlines(keepends=True)
    pos = 0
    i = 0
    pending_path = None
    pending_type = None
    block_start = 0
    code_lines = []
    fence_depth = 0
    is_markdown = False
    run_pending = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        current_pos = pos

        if pending_path:
            check_eof = (fence_depth == 0) or is_markdown
            if check_eof:
                em = _EOF_SIGNAL_LINE.search(stripped)
                if em:
                    eof_path = _extract_path(em)
                    # Bare EOF (no name) closes current block using pending_path
                    if not eof_path:
                        eof_path = pending_path
                    # Exact match always closes; for TOOL/SKILL blocks,
                    # also accept any EOF when block has content (models
                    # often write the file path instead of the tool name)
                    eof_matches = (eof_path == pending_path or
                                   (pending_type in ("tool", "skill") and code_lines))
                    if eof_matches:
                        pos += len(line)
                        i += 1
                        raw_code = "".join(code_lines)
                        code = _strip_surrounding_fences(raw_code)
                        yield (block_start, pos, pending_path, "", code, True, pending_type)
                        pending_path = None
                        pending_type = None
                        code_lines = []
                        fence_depth = 0
                        is_markdown = False
                        continue

            if stripped.startswith("```"):
                if re.match(r"```\w", stripped):
                    fence_depth += 1
                else:
                    fence_depth -= 1
                code_lines.append(line)
                pos += len(line)
                i += 1
                if fence_depth <= 0 and not is_markdown:
                    if i < len(lines):
                        next_stripped = lines[i].strip()
                        em = _EOF_SIGNAL_LINE.search(next_stripped)
                        if em and _extract_path(em) == pending_path:
                            pos += len(lines[i])
                            i += 1
                            raw_code = "".join(code_lines)
                            code = _strip_surrounding_fences(raw_code)
                            yield (block_start, pos, pending_path, "", code, True, pending_type)
                            pending_path = None
                            pending_type = None
                            code_lines = []
                            fence_depth = 0
                            is_markdown = False
                            continue
                    raw_code = "".join(code_lines)
                    code = _strip_surrounding_fences(raw_code)
                    yield (block_start, pos, pending_path, "", code, False, pending_type)
                    pending_path = None
                    pending_type = None
                    code_lines = []
                    fence_depth = 0
                    is_markdown = False
                continue

            if fence_depth == 0:
                wm_new = _WRITE_SIGNAL_LINE.search(stripped)
                em_new = _EDIT_SIGNAL_LINE.search(stripped)
                fm_new = _FILE_SIGNAL_LINE.search(stripped)
                tm_new = _TOOL_SIGNAL_LINE.search(stripped)
                sm_new = _SKILL_SIGNAL_LINE.search(stripped)
                if wm_new or em_new or fm_new or tm_new or sm_new:
                    run_pending = False
                    raw_code = "".join(code_lines)
                    code = _strip_surrounding_fences(raw_code)
                    yield (block_start, current_pos, pending_path, "", code, False, pending_type)
                    if wm_new:
                        pending_path = _extract_path(wm_new)
                        pending_type = "write"
                    elif em_new:
                        pending_path = _extract_path(em_new)
                        pending_type = "edit"
                        # EDIT blocks must only close on EOF
                        is_markdown = True
                    elif fm_new:
                        pending_path = _extract_path(fm_new)
                        pending_type = "file"
                    elif tm_new:
                        pending_path = _extract_path(tm_new)
                        pending_type = "tool"
                        # TOOL blocks close only on EOF
                        is_markdown = True
                    else:
                        pending_path = _extract_path(sm_new)
                        pending_type = "skill"
                        # SKILL blocks close only on EOF
                        is_markdown = True
                    block_start = current_pos
                    code_lines = []
                    fence_depth = 0
                    pos += len(line)
                    i += 1
                    continue

            code_lines.append(line)
            pos += len(line)
            i += 1
            continue

        if _RUN_SIGNAL_LINE.search(stripped):
            run_pending = True
            pos += len(line)
            i += 1
            continue

        fm = _FILE_SIGNAL_LINE.search(stripped)
        if fm:
            run_pending = False
            pending_path = _extract_path(fm)
            pending_type = "file"
            block_start = current_pos
            code_lines = []
            fence_depth = 0
            ext = os.path.splitext(pending_path)[1].lower()
            is_markdown = ext in ('.md', '.markdown', '.mdx')
            pos += len(line)
            i += 1
            continue

        em = _EDIT_SIGNAL_LINE.search(stripped)
        if em:
            run_pending = False
            pending_path = _extract_path(em)
            pending_type = "edit"
            block_start = current_pos
            code_lines = []
            fence_depth = 0
            # EDIT blocks must only close on EOF, not on fence depth,
            # because they can contain multiple ```search-replace``` blocks.
            is_markdown = True
            pos += len(line)
            i += 1
            continue

        wm = _WRITE_SIGNAL_LINE.search(stripped)
        if wm:
            run_pending = False
            pending_path = _extract_path(wm)
            pending_type = "write"
            block_start = current_pos
            code_lines = []
            fence_depth = 0
            ext = os.path.splitext(pending_path)[1].lower()
            is_markdown = ext in ('.md', '.markdown', '.mdx')
            pos += len(line)
            i += 1
            continue

        tm = _TOOL_SIGNAL_LINE.search(stripped)
        if tm:
            run_pending = False
            pending_path = _extract_path(tm)
            pending_type = "tool"
            block_start = current_pos
            code_lines = []
            fence_depth = 0
            # TOOL blocks must only close on EOF, not on fence depth,
            # because their content (JSON or key-value) may not have
            # balanced fences and the opening ``` would otherwise
            # immediately close the block.
            is_markdown = True
            pos += len(line)
            i += 1
            continue

        sm = _SKILL_SIGNAL_LINE.search(stripped)
        if sm:
            run_pending = False
            pending_path = _extract_path(sm)
            pending_type = "skill"
            block_start = current_pos
            code_lines = []
            fence_depth = 0
            # SKILL blocks must only close on EOF, not on fence depth,
            # for the same reason as TOOL blocks.
            is_markdown = True
            pos += len(line)
            i += 1
            continue

        fence_m = re.match(r"```(bash|sh|shell|cmd|bat|powershell|ps1|pwsh)", stripped)
        if fence_m:
            lang = fence_m.group(1)
            block_start = current_pos
            code_lines = []
            i += 1
            pos += len(line)
            depth = 1
            while i < len(lines):
                inner = lines[i]
                inner_s = inner.strip()
                if re.match(r"```\w+", inner_s):
                    depth += 1
                    code_lines.append(inner)
                elif inner_s.startswith("```") and not re.match(r"```\w", inner_s):
                    depth -= 1
                    if depth == 0:
                        pos += len(inner)
                        i += 1
                        break
                    else:
                        code_lines.append(inner)
                else:
                    code_lines.append(inner)
                pos += len(inner)
                i += 1
            if run_pending:
                code = "".join(code_lines).rstrip()
                yield (block_start, pos, None, lang, code, True, None)
            run_pending = False
            continue

        if stripped:
            run_pending = False
        pos += len(line)
        i += 1

    if pending_path:
        raw_code = "".join(code_lines)
        code = _strip_surrounding_fences(raw_code)
        yield (block_start, pos, pending_path, "", code, False, pending_type)


def parse_actions(text):
    """Parse all actionable blocks (WRITE, EDIT, RUN) from LLM response text."""
    actions = []
    write_spans = []
    for start, end, path, lang, code, closed, btype in _extract_blocks(text):
        if path and btype == "write":
            actions.append({"type": "write", "path": path, "lang": lang,
                            "code": code, "span": (start, end), "closed": closed})
            write_spans.append((start, end))
        elif path and btype == "edit":
            edits = parse_edit_content(code)
            actions.append({"type": "edit", "path": path, "edits": edits,
                            "code": code, "span": (start, end), "closed": closed})
            write_spans.append((start, end))
        elif path and btype == "file":
            actions.append({"type": "read", "path": path, "code": code,
                            "span": (start, end), "closed": closed})
            write_spans.append((start, end))
        elif path and btype == "tool":
            tool_params, tool_json_error = _parse_params(code)
            action = {"type": "tool", "name": path, "params": tool_params,
                            "code": code, "span": (start, end), "closed": closed}
            if tool_json_error:
                action["json_error"] = tool_json_error
            actions.append(action)
        elif path and btype == "skill":
            skill_params, skill_json_error = _parse_params(code)
            action = {"type": "skill", "name": path, "params": skill_params,
                            "code": code, "span": (start, end), "closed": closed}
            if skill_json_error:
                action["json_error"] = skill_json_error
            actions.append(action)
        elif lang in ("bash", "sh", "shell", "cmd", "bat", "powershell", "ps1", "pwsh") and code:
            if not any(s[0] <= start < s[1] for s in write_spans):
                actions.append({"type": "run", "code": code, "span": (start, end)})
    return actions
