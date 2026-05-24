"""File extension → language detection."""
from __future__ import annotations

from pathlib import Path

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".c": "c",
    ".h": "c",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".cs": "csharp",
    ".md": "markdown",
    ".rst": "restructuredtext",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".dockerfile": "dockerfile",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "scss",
    ".less": "less",
    ".xml": "xml",
    ".txt": "text",
    ".ini": "ini",
    ".env": "dotenv",
    ".cfg": "ini",
}

# Filenames whose extension is missing or non-indicative.
_NAME_TO_LANG: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "make",
    "CMakeLists.txt": "cmake",
}


def detect_language(path: Path) -> str | None:
    name = path.name
    if name in _NAME_TO_LANG:
        return _NAME_TO_LANG[name]
    return _EXT_TO_LANG.get(path.suffix.lower())
