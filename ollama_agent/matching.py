"""Fuzzy and exact line-based search/match for EDIT operations."""

import difflib


def _dedent_lines(lines):
    """Remove common leading whitespace from lines."""
    min_indent = float('inf')
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            min_indent = min(min_indent, len(line) - len(stripped))
    if min_indent == float('inf'):
        min_indent = 0
    return [line[min_indent:] if len(line) >= min_indent and line.strip() else line for line in lines]


def _search_lines_exact(haystack, needle):
    """Find exact line-for-line match. Returns (start, end) or None."""
    n = len(needle)
    if n == 0:
        return None
    for i in range(len(haystack) - n + 1):
        if haystack[i:i + n] == needle:
            return (i, i + n)
    return None


def _search_lines_stripped(haystack, needle):
    """Match ignoring trailing whitespace per line."""
    n = len(needle)
    if n == 0:
        return None
    sh = [l.rstrip() for l in haystack]
    sn = [l.rstrip() for l in needle]
    for i in range(len(sh) - n + 1):
        if sh[i:i + n] == sn:
            return (i, i + n)
    return None


def _search_lines_dedented(haystack, needle):
    """Match after dedenting both haystack window and needle."""
    n = len(needle)
    if n == 0:
        return None
    dedented_needle = _dedent_lines(needle)
    for i in range(len(haystack) - n + 1):
        if _dedent_lines(haystack[i:i + n]) == dedented_needle:
            return (i, i + n)
    return None


def _search_lines_fuzzy(haystack, needle, threshold=0.8):
    """Fuzzy match using SequenceMatcher ratio."""
    n = len(needle)
    if n == 0:
        return None
    needle_text = '\n'.join(needle)
    best_ratio = 0.0
    best_pos = None
    for i in range(max(1, len(haystack) - n + 1)):
        candidate_text = '\n'.join(haystack[i:i + n])
        ratio = difflib.SequenceMatcher(None, candidate_text, needle_text).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_pos = i
    if best_ratio >= threshold and best_pos is not None:
        return (best_pos, best_pos + n)
    return None


def find_match_in_content(file_content, search_text):
    """Find search_text in file_content using layered fuzzy matching.
    Returns (start_line, end_line, match_quality) or None.
    match_quality: 'exact', 'whitespace', 'dedented', or 'fuzzy'."""
    # Normalize line endings: CRLF (\r\n) and bare CR (\r) -> LF (\n)
    # This is critical on Windows where files often have \r\n line endings
    # but the model's SEARCH text uses \n.
    file_content = file_content.replace('\r\n', '\n').replace('\r', '\n')
    search_text = search_text.replace('\r\n', '\n').replace('\r', '\n')
    file_lines = file_content.split('\n')
    search_lines = search_text.split('\n')
    # Strip trailing empty strings from trailing newlines
    while file_lines and file_lines[-1] == '':
        file_lines.pop()
    while search_lines and search_lines[-1] == '':
        search_lines.pop()
    if not search_lines:
        return None
    result = _search_lines_exact(file_lines, search_lines)
    if result:
        return (*result, 'exact')
    result = _search_lines_stripped(file_lines, search_lines)
    if result:
        return (*result, 'whitespace')
    result = _search_lines_dedented(file_lines, search_lines)
    if result:
        return (*result, 'dedented')
    result = _search_lines_fuzzy(file_lines, search_lines)
    if result:
        return (*result, 'fuzzy')
    return None
