"""Minimal HTML sanitizer for stored consent bodies (XSS defence).

Strips ``<script>``/``<style>`` blocks, inline ``on*`` event handlers, and
``javascript:`` URLs. This is a pragmatic allowlist-free pass that removes the
common injection vectors for rich-text consent content. For hardened production
use, swap in a vetted library (``nh3``/``bleach``) behind this same function.
"""

from __future__ import annotations

import re

_SCRIPT_STYLE = re.compile(r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)
_ON_ATTR = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
_JS_URL = re.compile(r"(href|src)\s*=\s*(\"|')\s*javascript:[^\"']*(\2)", re.IGNORECASE)
_BARE_TAGS = re.compile(r"<\s*/?\s*(script|style|iframe|object|embed|link|meta)\b[^>]*>", re.IGNORECASE)


def sanitize_html(html: str | None) -> str | None:
    if not html:
        return html
    cleaned = _SCRIPT_STYLE.sub("", html)
    cleaned = _BARE_TAGS.sub("", cleaned)
    cleaned = _ON_ATTR.sub("", cleaned)
    cleaned = _JS_URL.sub(r"\1=\2#\2", cleaned)
    return cleaned
