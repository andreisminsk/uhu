"""Sensitive-file protection layer.

Gates file content before it enters the LLM context. With cloud models
(proxied via ollama.com or direct OpenAI-compatible endpoints), content
routinely leaves the machine — this layer ensures secrets don't leave
without explicit user confirmation.

Two detection tiers:
- Filename patterns (precise, near-zero false positives) → confirm/block
- Content patterns (net, higher FP) → redact only

Config (.ollama_agent.json → "privacy"):
- mode: "off" | "standard" | "strict"
- policy: "block" | "confirm" | "redact"  (filename tier)
- filename_patterns / content_patterns: override defaults
- allow: paths exempt from gating (matched by basename or relpath)
"""

import fnmatch
import os
import re

# ── Default patterns ────────────────────────────────────────────────────

DEFAULT_FILENAME_PATTERNS = [
    ".env", ".env.*", "*.env",
    "*.pem", "*.key", "*.pfx", "*.p12", "*.crt", "*.cer",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    "credentials*", "secrets*", "*_credentials*", "*_secrets*",
    ".gitconfig", ".npmrc", ".netrc", ".pypirc", ".aws/credentials",
    "cookies.txt", "*cookies*.txt",
    "*cred*.json", "*credential*.json",
    "settings.local.json", ".ollama_agent.json",
    "gs-cred.json", "service-account*.json",
    "*.kdbx", "*.keystore", "*.jks",
]

DEFAULT_ALLOW = [
    ".env.example", ".env.sample", ".env.template", ".env.test",
    "*.env.example", "example.env", "sample.env",
]

# Content patterns — redact only, never block (higher FP rate)
DEFAULT_CONTENT_PATTERNS = [
    # Private key blocks
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED PRIVATE KEY]"),
    # AWS access keys
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED AWS KEY]"),
    # Google API keys
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"), "[REDACTED API KEY]"),
    # GitHub tokens
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"), "[REDACTED TOKEN]"),
    # Slack tokens
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"), "[REDACTED TOKEN]"),
    # Generic assignments: KEY=VALUE where KEY looks secret-ish
    (re.compile(r"(?im)^(\s*(?:export\s+)?(?:API_KEY|SECRET|PASSWORD|PASSWD|TOKEN|CREDENTIALS?)[A-Z0-9_]*\s*=\s*)(\S.*)$"), r"\1[REDACTED]"),
]


# ── Policy decision ─────────────────────────────────────────────────────

class PolicyDecision:
    __slots__ = ("action", "reason")
    def __init__(self, action, reason=""):
        self.action = action  # "allow" | "confirm" | "block" | "redact"
        self.reason = reason


class PrivacyGate:
    """Checks paths and text against sensitive-file/content patterns."""

    def __init__(self, config=None):
        config = config or {}
        privacy = config.get("privacy", {}) if isinstance(config, dict) else {}
        self.mode = privacy.get("mode", "standard")
        self.policy = privacy.get("policy", "confirm")
        # Empty list in config = "use defaults" (not "disable")
        self.filename_patterns = list(privacy.get("filename_patterns") or DEFAULT_FILENAME_PATTERNS)
        self.allow = list(privacy.get("allow") or DEFAULT_ALLOW)
        # Compile content patterns (allow string patterns from config too)
        self.content_patterns = []
        for p in (privacy.get("content_patterns") or DEFAULT_CONTENT_PATTERNS):
            if isinstance(p, tuple):
                self.content_patterns.append((re.compile(p[0]), p[1]))
            else:
                self.content_patterns.append((re.compile(p), "[REDACTED]"))

    @property
    def enabled(self):
        return self.mode != "off"

    def _is_allowed(self, basename, relpath):
        for pat in self.allow:
            if fnmatch.fnmatch(basename, pat) or fnmatch.fnmatch(relpath, pat):
                return True
        return False

    def check_path(self, path, workdir=None):
        """Check a file path. Returns PolicyDecision."""
        if not self.enabled:
            return PolicyDecision("allow")
        basename = os.path.basename(path.rstrip("/\\")) or path
        relpath = path
        if workdir and not os.path.isabs(path):
            relpath = os.path.relpath(os.path.join(workdir, path), workdir)
        if self._is_allowed(basename, relpath):
            return PolicyDecision("allow")
        for pat in self.filename_patterns:
            if fnmatch.fnmatch(basename, pat) or fnmatch.fnmatch(relpath, pat):
                if self.mode == "strict":
                    return PolicyDecision("block", f"sensitive file (matched pattern '{pat}')")
                if self.policy == "redact":
                    return PolicyDecision("redact", f"sensitive file (matched pattern '{pat}')")
                return PolicyDecision(self.policy, f"sensitive file (matched pattern '{pat}')")
        return PolicyDecision("allow")

    def scan_text(self, text):
        """Scan text for secret-shaped content. Returns list of (pattern_desc, count)."""
        if not self.enabled or not text:
            return []
        findings = []
        for rx, _repl in self.content_patterns:
            n = len(rx.findall(text))
            if n:
                findings.append((rx.pattern[:40], n))
        return findings

    def redact(self, text):
        """Redact secret-shaped content from text. Returns (text, n_redactions)."""
        if not self.enabled or not text:
            return text, 0
        n_total = 0
        for rx, repl in self.content_patterns:
            text, n = rx.subn(repl, text)
            n_total += n
        return text, n_total
