"""Edit summary and diff generation utilities."""

import difflib


def make_edit_summary(path, edits_applied):
    """Generate a human-readable summary of applied edits."""
    parts = [f"[EDIT] {path} ({len(edits_applied)} change(s))"]
    for start, end, quality, search_text, replace_text in edits_applied:
        sl = len(search_text.split('\n'))
        rl = len(replace_text.split('\n'))
        if sl == rl:
            desc = f"replaced {sl} line(s)"
        elif sl == 0:
            desc = f"inserted {rl} line(s)"
        elif rl == 0:
            desc = f"deleted {sl} line(s)"
        else:
            desc = f"replaced {sl} line(s) with {rl} line(s)"
        q = f" [{quality} match]" if quality != 'exact' else ""
        parts.append(f"  L{start + 1}-{end}: {desc}{q}")
    return '\n'.join(parts)


def make_unified_diff(path, original, new):
    """Generate a unified diff string between original and new content."""
    orig_lines = original.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(orig_lines, new_lines,
                                       fromfile=f"a/{path}", tofile=f"b/{path}",
                                       lineterm='\n'))
    if not diff:
        return "(no changes)"
    if len(diff) > 200:
        diff = diff[:200] + [f"... ({len(diff) - 200} more diff lines)\n"]
    return ''.join(diff)
