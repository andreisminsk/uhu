import re
import urllib.parse

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ollama_agent.tools.web_search import _parse_ddg_lite


def test_parse_ddg_lite_with_real_html():
    """Test that _parse_ddg_lite correctly parses DDG Lite HTML with single-quoted attributes."""
    # Simplified DDG Lite HTML structure (uses single quotes for class attributes)
    html = """<html><body>
    <tr><td><a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FDMC_DeLorean&amp;rut=abc" class='result-link'>DMC DeLorean - Wikipedia</a></td></tr>
    <tr><td class='result-snippet'>The DMC DeLorean is a rear-engine sports car</td></tr>
    <tr><td><a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdelorean.com%2F&amp;rut=def" class='result-link'>DeLorean Motor Company</a></td></tr>
    <tr><td class='result-snippet'>DeLorean is a legacy mobility company</td></tr>
    </body></html>"""
    results = _parse_ddg_lite(html, 5)
    assert len(results) == 2, f"Expected 2 results, got {len(results)}"
    assert results[0]["title"] == "DMC DeLorean - Wikipedia"
    assert results[0]["url"] == "https://en.wikipedia.org/wiki/DMC_DeLorean"
    assert "rear-engine" in results[0]["snippet"]
    assert results[1]["title"] == "DeLorean Motor Company"
    assert results[1]["url"] == "https://delorean.com/"


def test_parse_ddg_lite_double_quotes():
    """Test parsing with double-quoted class attributes."""
    html = """<html><body>
    <tr><td><a href="https://example.com" class="result-link">Example</a></td></tr>
    <tr><td class="result-snippet">Example snippet</td></tr>
    </body></html>"""
    results = _parse_ddg_lite(html, 5)
    assert len(results) == 1
    assert results[0]["title"] == "Example"
    assert results[0]["url"] == "https://example.com"
    assert results[0]["snippet"] == "Example snippet"


def test_parse_ddg_lite_uddg_redirect():
    """Test that uddg redirect URLs are properly decoded."""
    html = """<html><body>
    <tr><td><a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpath&amp;rut=xyz" class='result-link'>Test</a></td></tr>
    <tr><td class='result-snippet'>Test snippet</td></tr>
    </body></html>"""
    results = _parse_ddg_lite(html, 5)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/path"


def test_parse_ddg_lite_empty():
    """Test that empty HTML returns no results."""
    results = _parse_ddg_lite("<html><body></body></html>", 5)
    assert len(results) == 0


if __name__ == "__main__":
    test_parse_ddg_lite_with_real_html()
    test_parse_ddg_lite_double_quotes()
    test_parse_ddg_lite_uddg_redirect()
    test_parse_ddg_lite_empty()
    print("All tests passed!")
