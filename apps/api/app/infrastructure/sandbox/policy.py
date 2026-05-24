"""Command classification for the sandbox (Phase 5).

The sandbox container is already heavily locked down (no network, dropped
capabilities, read-only root, non-root user, resource caps, ephemeral). This
classifier is *defense-in-depth* + UX: it blocks obviously catastrophic
commands outright, and flags risky-looking ones so the UI can require an
explicit user approval before running.

Verdicts:
  - blocked:  never run (host-destructive patterns, container-escape attempts)
  - approval: run only after explicit user confirmation
  - allow:    run immediately
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Verdict = Literal["allow", "approval", "blocked"]


@dataclass(slots=True)
class Classification:
    verdict: Verdict
    reason: str


# Hard blocks — patterns that should never execute even inside the sandbox.
# (Most are already neutralized by no-network + dropped caps, but defense in depth.)
_BLOCK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME)(\*|\s|$)"), "recursive delete of a root/home path"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"), "fork bomb"),
    (re.compile(r"\b(mkfs|fdisk|parted)\b"), "filesystem/partition tool"),
    (re.compile(r"\bdd\b.*\bof=/dev/"), "raw write to a device"),
    (re.compile(r">\s*/dev/(sd|nvme|hd)[a-z]"), "write to a block device"),
    (re.compile(r"\b(shutdown|reboot|halt|poweroff)\b"), "host power control"),
    (re.compile(r"/var/run/docker\.sock|/var/lib/docker"), "docker socket / daemon access"),
    (re.compile(r"\bdocker\b\s+(run|exec|rm|build|--privileged)"), "nested docker control"),
    (re.compile(r"\bmount\b|\bumount\b"), "mount operation"),
    (re.compile(r"\bchroot\b"), "chroot"),
]

# Needs explicit approval — risky but legitimate (writes, installs, etc.).
_APPROVAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(curl|wget|nc|netcat|ssh|scp|telnet)\b"), "network access (will fail — sandbox has no network)"),
    (re.compile(r"\b(pip|pip3|npm|yarn|pnpm|apt|apt-get|apk|conda)\s+(install|add|i)\b"), "package install"),
    (re.compile(r"\bsudo\b"), "privilege escalation attempt"),
    (re.compile(r"\brm\s+-[a-z]*r"), "recursive delete"),
    (re.compile(r">\s*/(etc|usr|bin|lib|var)\b"), "write outside the workspace"),
    (re.compile(r"\bgit\s+push\b"), "git push"),
]


def classify(command: str) -> Classification:
    cmd = (command or "").strip()
    if not cmd:
        return Classification("blocked", "empty command")
    if len(cmd) > 4000:
        return Classification("blocked", "command too long")

    for pat, reason in _BLOCK_PATTERNS:
        if pat.search(cmd):
            return Classification("blocked", reason)
    for pat, reason in _APPROVAL_PATTERNS:
        if pat.search(cmd):
            return Classification("approval", reason)
    return Classification("allow", "no risky patterns detected")
