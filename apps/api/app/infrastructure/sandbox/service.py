"""Sandbox execution service (Phase 5).

Runs a single shell command inside a throwaway, hardened Docker container and
streams its combined stdout/stderr back to the caller. The container is a
*sibling* spawned through the host Docker socket (mounted into the api).

Isolation applied to every sandbox container:
  - network_mode = "none"            → no network at all
  - cap_drop = ["ALL"]               → no Linux capabilities
  - security_opt no-new-privileges   → cannot gain privileges
  - read_only root filesystem        → cannot modify the image
  - tmpfs /workspace (size-capped)   → the only writable area
  - non-root user (1000:1000)
  - mem_limit / nano_cpus / pids_limit → resource caps (anti-DoS / fork-bomb)
  - hard wall-clock timeout          → killed if it overruns
  - auto-remove                      → no lingering containers
  - the selected repo is mounted READ-ONLY at /workspace/repo

The blocking docker SDK runs in a thread; output lines are pushed onto an
asyncio.Queue so the WebSocket layer can stream them.
"""
from __future__ import annotations

import asyncio
import shlex
import threading
from dataclasses import dataclass
from typing import Any, AsyncIterator

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("sandbox")


@dataclass(slots=True)
class SandboxEvent:
    kind: str           # "output" | "status" | "exit" | "error"
    text: str = ""
    exit_code: int | None = None


class SandboxError(Exception):
    pass


def _docker_client():
    import docker

    # Talks to the socket mounted at /var/run/docker.sock.
    return docker.from_env()


class SandboxService:
    def __init__(self) -> None:
        self._image = settings.sandbox_image
        self._timeout = settings.sandbox_timeout_seconds
        self._max_output = settings.sandbox_max_output_bytes

    def _build_container_kwargs(self, command: str, repo_subpath: str | None) -> dict[str, Any]:
        # When a repo is selected, mount the cloned-repos volume read-only and
        # copy just that repo into the writable tmpfs before running — so the
        # command gets a real working tree and writes never touch the original.
        if repo_subpath:
            inner = (
                f"cp -a /repo-root/{shlex.quote(repo_subpath)}/. /workspace/ 2>/dev/null || true; "
                f"cd /workspace; {command}"
            )
        else:
            inner = f"cd /workspace; {command}"

        kwargs: dict[str, Any] = {
            "image": self._image,
            "command": ["sh", "-lc", inner],
            "detach": True,
            "network_mode": "none",
            "mem_limit": settings.sandbox_mem_limit,
            "nano_cpus": int(settings.sandbox_cpus * 1_000_000_000),
            "pids_limit": settings.sandbox_pids_limit,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
            "read_only": True,
            "user": "1000:1000",
            "working_dir": "/workspace",
            "tmpfs": {
                "/workspace": f"size={settings.sandbox_workspace_tmpfs_size},mode=1777",
                "/tmp": "size=64m,mode=1777",
            },
            "environment": {"HOME": "/workspace", "PATH": "/usr/local/bin:/usr/bin:/bin"},
            "labels": {"aca.sandbox": "true"},
            "auto_remove": False,   # we remove explicitly after reading exit code
        }
        if repo_subpath:
            kwargs["volumes"] = {
                settings.sandbox_workspace_volume: {"bind": "/repo-root", "mode": "ro"}
            }
        return kwargs

    async def run_stream(
        self, *, command: str, repo_subpath: str | None
    ) -> AsyncIterator[SandboxEvent]:
        """Run `command` in a fresh sandbox; yield output/status/exit events."""
        if not settings.sandbox_enabled:
            yield SandboxEvent("error", text="sandbox is disabled")
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[SandboxEvent | None] = asyncio.Queue()

        def _worker() -> None:
            client = None
            container = None
            sent = 0
            try:
                client = _docker_client()
                kwargs = self._build_container_kwargs(command, repo_subpath)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    SandboxEvent("status", text=f"starting sandbox ({self._image})"),
                )
                container = client.containers.run(**kwargs)

                # Watchdog: kill the container if it overruns the timeout.
                killed = {"v": False}

                def _watchdog() -> None:
                    if not _stop.wait(self._timeout):
                        killed["v"] = True
                        try:
                            container.kill()
                        except Exception:
                            pass

                _stop = threading.Event()
                wd = threading.Thread(target=_watchdog, daemon=True)
                wd.start()

                # Stream combined stdout/stderr.
                for raw in container.logs(stream=True, follow=True, stdout=True, stderr=True):
                    chunk = raw.decode("utf-8", errors="replace")
                    sent += len(chunk)
                    if sent > self._max_output:
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            SandboxEvent("status", text="[output truncated — limit reached]"),
                        )
                        try:
                            container.kill()
                        except Exception:
                            pass
                        break
                    loop.call_soon_threadsafe(
                        queue.put_nowait, SandboxEvent("output", text=chunk)
                    )

                _stop.set()
                try:
                    result = container.wait(timeout=5)
                    code = int(result.get("StatusCode", -1))
                except Exception:
                    code = -1
                if killed["v"]:
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        SandboxEvent("status", text=f"[killed: exceeded {self._timeout}s timeout]"),
                    )
                loop.call_soon_threadsafe(
                    queue.put_nowait, SandboxEvent("exit", exit_code=code)
                )
            except Exception as exc:  # pragma: no cover
                log.error("sandbox_run_failed", error=f"{type(exc).__name__}: {exc}")
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    SandboxEvent("error", text=f"{type(exc).__name__}: {exc}"),
                )
            finally:
                if container is not None:
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass
                loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
