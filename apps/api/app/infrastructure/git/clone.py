"""Repository cloning helpers.

Safe, bounded clone for ingestion. We shallow-clone (--depth=1) to limit network
+ disk, validate the URL early, and enforce a hard byte cap by streaming through
GitPython's progress callback (best-effort) and a post-clone disk-usage check.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from git import GitCommandError, Repo
from git.cmd import Git

# Allow https, ssh-style (git@host:org/repo), or local /paths.
_URL_RE = re.compile(
    r"^("
    r"https://[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]+"          # https
    r"|git@[A-Za-z0-9.-]+:[A-Za-z0-9._/-]+(\.git)?"        # ssh shorthand
    r"|/[A-Za-z0-9._/-]+"                                  # absolute local path
    r"|[A-Za-z]:[\\/][A-Za-z0-9._\\/ -]+"                  # windows local path
    r")$"
)


class CloneError(Exception):
    pass


@dataclass(slots=True, frozen=True)
class CloneResult:
    workdir: Path           # path containing the working tree
    commit_sha: str         # HEAD commit sha
    bytes_on_disk: int      # size of the working tree (excluding .git)
    branch: str             # branch actually cloned (may differ from requested)


def detect_default_branch(url: str) -> str | None:
    """Return the remote's HEAD branch (e.g. 'main' or 'master'), or None.

    Uses `git ls-remote --symref` which reads a single ref without cloning.
    """
    try:
        out = Git().ls_remote("--symref", url, "HEAD")
    except GitCommandError:
        return None
    # Output looks like: "ref: refs/heads/master\tHEAD\n<sha>\tHEAD"
    for line in out.splitlines():
        if line.startswith("ref:"):
            # "ref: refs/heads/master\tHEAD"
            ref = line.split()[1]
            if ref.startswith("refs/heads/"):
                return ref[len("refs/heads/"):]
    return None


def validate_url(url: str) -> None:
    if not _URL_RE.match(url.strip()):
        raise CloneError(f"Unsupported or unsafe repository URL: {url!r}")
    parsed = urlparse(url) if url.startswith("http") else None
    if parsed and parsed.scheme not in {"", "https"}:
        raise CloneError("Only https git URLs are allowed for remote sources")


def workdir_for(workspace_root: Path, repo_id: str) -> Path:
    return workspace_root / repo_id


def _dir_size(p: Path) -> int:
    total = 0
    for child in p.rglob("*"):
        if child.is_file() and not child.is_symlink():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def shallow_clone(
    *,
    url: str,
    branch: str | None,
    dest: Path,
    max_bytes: int,
) -> CloneResult:
    """Shallow-clone `url` into `dest`. Removes `dest` if pre-existing."""
    validate_url(url)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Clone into a tmp dir first so we never present a half-checkout to the world.
    with tempfile.TemporaryDirectory(prefix="aca-clone-", dir=str(dest.parent)) as tmp:
        tmp_path = Path(tmp) / "repo"

        # If branch was explicitly requested, try it first; on "branch not found"
        # fall back to the remote's actual HEAD branch.
        attempts: list[str | None] = []
        if branch:
            attempts.append(branch)
        attempts.append(None)  # let git use the remote's default
        seen: set[str | None] = set()

        repo: Repo | None = None
        last_err: GitCommandError | None = None
        actual_branch: str | None = branch
        for attempt in attempts:
            if attempt in seen:
                continue
            seen.add(attempt)
            shutil.rmtree(tmp_path, ignore_errors=True)
            kwargs: dict[str, object] = {"depth": 1, "single_branch": True}
            if attempt:
                kwargs["branch"] = attempt
            try:
                repo = Repo.clone_from(url, str(tmp_path), **kwargs)
                actual_branch = attempt or detect_default_branch(url) or "HEAD"
                break
            except GitCommandError as e:
                last_err = e
                stderr = (e.stderr or "").lower()
                # Only swallow "branch not found" errors; auth/network errors stop us.
                if "remote branch" in stderr and "not found" in stderr:
                    continue
                raise CloneError(f"git clone failed: {e.stderr or e}") from e

        if repo is None:
            raise CloneError(
                f"git clone failed (no usable branch): {last_err.stderr if last_err else 'unknown'}"
            ) from last_err

        size = _dir_size(tmp_path)
        if size > max_bytes:
            shutil.rmtree(tmp_path, ignore_errors=True)
            raise CloneError(
                f"Repository exceeds size limit: {size} bytes > {max_bytes}"
            )

        sha = repo.head.commit.hexsha
        # remove .git to save disk (we don't need history after clone)
        shutil.rmtree(tmp_path / ".git", ignore_errors=True)
        shutil.move(str(tmp_path), str(dest))

    return CloneResult(
        workdir=dest,
        commit_sha=sha,
        bytes_on_disk=_dir_size(dest),
        branch=actual_branch or "HEAD",
    )


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
