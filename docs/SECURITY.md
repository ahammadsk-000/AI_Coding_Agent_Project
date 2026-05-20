# Security

## Threat model (summary)

| Asset                  | Threat                          | Mitigation                                |
|------------------------|---------------------------------|-------------------------------------------|
| User credentials       | Theft, brute force              | Argon2id, per-IP & per-account rate limit |
| Access tokens          | Replay, theft                   | Short TTL (15m), refresh rotation         |
| Refresh tokens         | Long-lived theft                | DB-backed, revocable, jti tracking        |
| User code              | Exfiltration via prompt inj.    | Sandbox network deny, no outbound by default |
| Sandbox runtimes       | Container escape, resource abuse| User namespaces, seccomp, cgroup limits   |
| LLM tokens / API keys  | Leak via logs                   | Secrets manager only, redaction in logs   |
| Database               | Privilege escalation            | Per-service role, least privilege         |
| GitHub tokens          | Misuse                          | Per-install short-lived tokens (App)      |

## Auth

- Passwords: **Argon2id** via `passlib.hash.argon2`.
- Access token: JWT, HS256 in dev, **RS256 in prod**, 15-minute TTL.
- Refresh token: opaque 256-bit random, DB-stored hash, 30-day TTL, single-use rotation.
- Logout revokes the active refresh token (sets `revoked_at`).
- `Authorization: Bearer <access>` for all protected endpoints.

## RBAC

Phase 1: global roles `admin`, `member`, `viewer`.
Phase 10: org-scoped + resource-scoped permissions.

```python
@router.post("/repos", dependencies=[Depends(require_role("member", "admin"))])
```

## Rate limiting

Sliding-window in Redis. Defaults (overridable per route via decorator):
- Anonymous: 30 req/min/IP
- Authenticated: 300 req/min/user
- Auth endpoints (`/login`, `/register`): 10 req/min/IP, hard 429 after burst

## Sandboxing (Phase 5)

- Each execution gets a fresh container from a warm pool.
- `--network=none` by default; allowlist via repo config.
- `--cap-drop=ALL`, `--security-opt=no-new-privileges`, seccomp default.
- cgroup v2 caps: 1 CPU, 1 GiB RAM, 60s wall, 256 MiB tmp.
- Filesystem: read-only root, `/work` is a tmpfs scratch mount.

## Secrets

- Dev: `.env` (gitignored), `.env.example` is the contract.
- Prod: Kubernetes secrets sourced from cloud secret manager (External Secrets Operator).
- Never log secret values. `core.logging` has a redactor for `Authorization`, `password`, `token`, `api_key`.

## Audit logging

Every authn event and every mutation on sensitive resources writes to `audit_logs` with
user, action, resource, ip, user_agent, and an arbitrary JSON metadata blob.

## Headers

Set by middleware:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (prod only)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Content-Security-Policy: default-src 'self'` (tightened per route as needed)

## Dependency hygiene

- `pip-audit` and `npm audit` in CI.
- Dependabot for security updates.
- Pinned base images, multi-stage builds, non-root user in every container.
