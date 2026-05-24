"""Thin async GitHub REST client (Phase 6).

Covers exactly the operations the platform needs: identity check, repo lookup,
branch creation, file commit, PR creation, PR diff fetch, and issue/PR comment.
Auth is a Personal Access Token passed as a bearer header.
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from app.core.config import settings


class GitHubError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub {status}: {message}")
        self.status = status
        self.message = message


class GitHubClient:
    def __init__(self, token: str | None = None, base: str | None = None) -> None:
        self._token = token or settings.github_token
        self._base = (base or settings.github_api_base).rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-coding-agent",
        }

    async def _request(
        self, method: str, path: str, *, accept: str | None = None, **kwargs: Any
    ) -> httpx.Response:
        if not self._token:
            raise GitHubError(401, "no GitHub token configured (set GITHUB_TOKEN)")
        url = f"{self._base}{path}"
        headers = self._headers(accept) if accept else self._headers()
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
        if resp.status_code >= 400:
            msg = resp.text[:300]
            try:
                msg = resp.json().get("message", msg)
            except Exception:
                pass
            raise GitHubError(resp.status_code, msg)
        return resp

    # ---- identity / repo ----
    async def whoami(self) -> dict[str, Any]:
        return (await self._request("GET", "/user")).json()

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return (await self._request("GET", f"/repos/{owner}/{repo}")).json()

    # ---- branches ----
    async def get_branch_sha(self, owner: str, repo: str, branch: str) -> str:
        data = (await self._request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}")).json()
        return data["object"]["sha"]

    async def create_branch(self, owner: str, repo: str, new_branch: str, from_sha: str) -> None:
        await self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{new_branch}", "sha": from_sha},
        )

    # ---- contents (commit a single file) ----
    async def get_file_sha(self, owner: str, repo: str, path: str, branch: str) -> str | None:
        try:
            data = (
                await self._request(
                    "GET", f"/repos/{owner}/{repo}/contents/{path}", params={"ref": branch}
                )
            ).json()
            return data.get("sha")
        except GitHubError as e:
            if e.status == 404:
                return None
            raise

    async def put_file(
        self,
        owner: str,
        repo: str,
        *,
        path: str,
        content: str,
        message: str,
        branch: str,
    ) -> dict[str, Any]:
        existing_sha = await self.get_file_sha(owner, repo, path, branch)
        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if existing_sha:
            body["sha"] = existing_sha
        return (
            await self._request("PUT", f"/repos/{owner}/{repo}/contents/{path}", json=body)
        ).json()

    # ---- pull requests ----
    async def create_pull(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        draft: bool = False,
    ) -> dict[str, Any]:
        return (
            await self._request(
                "POST",
                f"/repos/{owner}/{repo}/pulls",
                json={"title": title, "head": head, "base": base, "body": body, "draft": draft},
            )
        ).json()

    async def get_pull(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        return (await self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}")).json()

    async def get_pull_diff(self, owner: str, repo: str, number: int) -> str:
        resp = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{number}",
            accept="application/vnd.github.v3.diff",
        )
        return resp.text

    async def comment_on_issue(self, owner: str, repo: str, number: int, body: str) -> dict[str, Any]:
        # PRs are issues for the comments API.
        return (
            await self._request(
                "POST",
                f"/repos/{owner}/{repo}/issues/{number}/comments",
                json={"body": body},
            )
        ).json()
