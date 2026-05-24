# AI Coding Agent — Helm chart

Deploys the full platform (api, worker, web) plus bundled postgres, redis, and
qdrant. Production concerns included: HPA, PodDisruptionBudget, NetworkPolicy,
Ingress, ConfigMap/Secret split, readiness/liveness probes.

## Prerequisites

- A Kubernetes cluster (Docker Desktop K8s, kind, minikube, or real).
- `kubectl` + `helm` 3.x.
- The app images available to the cluster:
  - `ai-coding-agent-api:latest`, `ai-coding-agent-worker:latest`, `ai-coding-agent-web:latest`
  - Build them via the repo's `docker compose build`. For kind: `kind load docker-image ai-coding-agent-api:latest` (and the others). Docker Desktop K8s sees local images directly.

## Quick start (local dev)

```bash
# from repo root
kubectl create namespace aca

helm install aca ./infra/helm/aca \
  -n aca \
  -f ./infra/helm/aca/values-dev.yaml

kubectl -n aca get pods -w
```

Dev values use single replicas, no autoscaling, `imagePullPolicy: Never`
(local images), and disable NetworkPolicy.

## Production-ish

```bash
helm install aca ./infra/helm/aca -n aca \
  --set images.api=ghcr.io/you/aca-api:1.2.3 \
  --set images.worker=ghcr.io/you/aca-worker:1.2.3 \
  --set images.web=ghcr.io/you/aca-web:1.2.3 \
  --set global.imageRegistry="" \
  --set secrets.jwtSecret="$(openssl rand -hex 32)" \
  --set secrets.postgresPassword="$(openssl rand -hex 16)" \
  --set ingress.host=aca.example.com \
  --set ingress.tls.enabled=true
```

For real production, set `postgres.enabled=false` / `redis.enabled=false` and
point `DATABASE_URL` / `REDIS_URL` at managed services via the ConfigMap
(or extend the chart to template those from values).

## Validate without a cluster

```bash
# lint
docker run --rm -v "$PWD/infra/helm/aca:/chart" alpine/helm:latest lint /chart

# render to plain manifests
docker run --rm -v "$PWD/infra/helm/aca:/chart" alpine/helm:latest \
  template aca /chart -f /chart/values-dev.yaml
```

## Upgrade / uninstall

```bash
helm upgrade aca ./infra/helm/aca -n aca -f ./infra/helm/aca/values-dev.yaml
helm uninstall aca -n aca
```

## Notes / limitations

- Bundled postgres/qdrant are single-replica StatefulSets — fine for dev/staging,
  not HA. Use managed databases or operators for production.
- `host.docker.internal` (Ollama) only resolves on Docker Desktop. On a real
  cluster, point `config.OLLAMA_BASE_URL` at a reachable Ollama, or use OpenAI.
- The web image runs the Vite dev server. For production build the `prod`
  (nginx) target and set `web.containerPort=80` + `web.command`.
