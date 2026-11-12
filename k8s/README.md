# BondCheck on Kubernetes

BondCheck runs on Kubernetes as a horizontally scaled API tier. Incoming requests are spread across several FastAPI + LangGraph replicas behind the Kubernetes Gateway API, and every response shows which pod served it.

```
                          ┌──────────────────── namespace: bondcheck ─────────────────────┐
 browser ──▶ Envoy Gateway ──/backend/*──▶ Service bondcheck-api ──▶ api pod 1 ┐            │
  :8080      (Gateway API,   least-request,  (prefix stripped)     ──▶ api pod 2 ├─▶ postgres │
             HTTPRoute)      passive health                        ──▶ api pod N ┘  (StatefulSet,
                    └──────/*──────────▶ Service bondcheck-frontend ──▶ next.js ×2     PVC)
                                                                                           │
   HPA: 3–10 api pods on CPU      PDBs      NetworkPolicies      CronJobs: Monitor, Alert  │
   Job: schema migration + demo seed (once per deploy)                                     │
                          └───────────────────────────────────────────────────────────────┘
```

## Quick start (local, about 10 minutes)

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/), [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation), [kubectl](https://kubernetes.io/docs/tasks/tools/) and [Helm](https://helm.sh/docs/intro/install/). On Windows: `winget install Docker.DockerDesktop Kubernetes.kind Kubernetes.kubectl Helm.Helm`, then start Docker Desktop.

```bash
cd bondcheck
scripts/k8s-up.sh          # Git Bash on Windows; creates the cluster, builds, deploys
```

Open <http://localhost:8080>. The gateway is reached directly: Envoy runs as a NodePort (30080,
[k8s/cluster/envoyproxy.yaml](cluster/envoyproxy.yaml)) that kind maps to `localhost:8080`
([k8s/kind-config.yaml](kind-config.yaml)), so no `kubectl port-forward` sits in the path and the
site stays up while Docker Desktop runs. Then:

```bash
python scripts/loadtest.py                         # 400 requests: see them spread over the API pods
python scripts/loadtest.py --duration 180 -c 40 --scenario mixed   # sustained load for the autoscaler
kubectl -n bondcheck get hpa,pods -w               # watch replicas scale from 3 up to 10
```

Example output:

```
Requests per pod (X-Served-By):
  bondcheck-api-7d9c6b8f5-kx2mq     137  34.2%  ##############
  bondcheck-api-7d9c6b8f5-p8vzn     133  33.2%  #############
  bondcheck-api-7d9c6b8f5-wq4tl     130  32.5%  #############
```

Tear down with `scripts/k8s-down.sh`.

## What's in `k8s/`

| File | What it does |
|---|---|
| `base/api.yaml` | **Deployment** (3 replicas, rolling update with `maxUnavailable: 0`, spread across nodes, non-root, startup/liveness/readiness probes, `preStop` drain). **Service**. **HPA** (CPU 70%, 3→10 pods, slow scale-down). **PodDisruptionBudget**. |
| `base/frontend.yaml` | Next.js standalone server: Deployment (2 replicas), Service, PDB. |
| `base/postgres.yaml` | PostgreSQL 17 **StatefulSet** with a PersistentVolumeClaim and a headless Service. |
| `base/gateway.yaml` | **Gateway API**: `Gateway`, two `HTTPRoute`s (`/backend/*` → API with the prefix stripped, `/*` → frontend), and an Envoy `BackendTrafficPolicy` (least-request load balancing, passive health checks). |
| `base/jobs.yaml` | **Job** `bondcheck-migrate` (schema + demo seed if the database is empty). **CronJobs** for the Monitor (08:00 IST) and Alert (08:15 IST) agents. |
| `base/network-policy.yaml` | Only API and migrate pods can reach Postgres. Only the gateway, peer API pods and cron jobs can reach the API. |
| `base/config.yaml` | ConfigMap of non-secret settings. |
| `cluster/gatewayclass.yaml` | Cluster-scoped `GatewayClass` bound to Envoy Gateway. |
| `overlays/local` | In-cluster Postgres, locally built `:dev` images, secrets from `secrets.env`. |
| `overlays/external-db` | Managed Postgres (Supabase/Neon): removes the StatefulSet, reads `DATABASE_URL` from the secret, uses GHCR images. |
| `kind-config.yaml` | Local cluster with 1 control plane and 2 workers. |

## Design decisions

**Why least-request, not round-robin.** Request costs vary a lot. A cached `/companies` takes milliseconds, while an upload runs five agents (OCR, PII redaction, extraction with self-checks, verification) for seconds. Round-robin can stack several slow uploads on one pod. Least-request sends each request to the replica with the fewest requests in flight.

**Keeping a human-in-the-loop pause working across replicas.** When the Extraction Agent isn't sure about a field, the LangGraph run pauses with `interrupt()` and waits for the uploader. That checkpoint stays in the pod's memory on purpose: earlier graph steps contain the raw, unredacted letter, and BondCheck promises that documents never reach disk. A shared Postgres checkpointer would break that promise. Sticky sessions would break even load balancing.

The solution (`core/cluster.py`):

1. The pod that pauses an upload records `upload_id → its pod IP` in the `upload_owners` table. The row holds no document data.
2. A `POST /upload/{id}/confirm` can land on any replica. If that replica doesn't hold the checkpoint, it looks up the owner and forwards the request pod-to-pod, then streams the owner's NDJSON response back. The `X-Upload-Owner` response header names the pod that did the work.
3. If the owner pod is gone (scale-down, crash), the upload expires with a clear 404. A single server behaves the same way after a restart. The HPA scales down slowly (one pod per minute, after a 3-minute window) to make this rare.

`tests/test_cluster.py` simulates two pods in one process and checks the forwarding path end to end.

**Probes split by purpose.** `/health` (liveness) doesn't touch the database, so a database outage doesn't trigger a restart storm. `/ready` (readiness) runs `SELECT 1`, so a pod that can't reach Postgres stops receiving traffic.

**Zero-downtime rollouts.** `maxUnavailable: 0` plus readiness gating means a new pod must be Ready before an old one is removed. The `preStop` sleep gives Envoy time to drop the endpoint, and uvicorn's 25-second graceful shutdown lets in-flight agent streams finish. CI runs a rolling restart under live load and requires at least 99% success.

**Safe concurrent startup.** Several API pods and the migrate Job may run `CREATE TABLE IF NOT EXISTS` at the same moment. Schema setup takes a Postgres advisory lock (`pg_advisory_xact_lock`), so they run one at a time.

**Database connections.** Each pod keeps a pool of 5 connections (`DB_POOL_SIZE`). At 10 pods that's 50 connections, well under the in-cluster Postgres `max_connections=200`. With Supabase, use the Session pooler URI.

**Known trade-off.** The 30-second read cache (`/companies`, `/stats`, …) is per pod, so after an upload another replica may show slightly older data for up to 30 seconds. To remove that window, move the cache to Redis.

## Deploying to a managed cluster (GKE / EKS / AKS)

1. Push to `main`. The `kubernetes` workflow publishes `ghcr.io/<you>/bondcheck-api` and `bondcheck-frontend`.
2. Install Envoy Gateway: `helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.9.3 -n envoy-gateway-system --create-namespace`, then `kubectl apply -f k8s/cluster/`.
3. In `k8s/overlays/external-db/kustomization.yaml`, check the image names (`ghcr.io/saipranav13188/...`). Copy `secrets.env.example` to `secrets.env` and fill it in.
4. Run `kubectl apply -k k8s/overlays/external-db`. The Gateway gets a cloud load balancer IP (`kubectl -n bondcheck get gateway`). Set `SITE_URL`/`CORS_ORIGINS` in `base/config.yaml` to your domain.

## CI (`.github/workflows/k8s.yml`)

- **validate**: renders both overlays with kustomize and schema-checks them with kubeconform, including Gateway API and Envoy CRDs.
- **e2e**: creates a 3-node kind cluster, runs `scripts/k8s-up.sh`, sends 600 mixed requests through the gateway (fails unless at least 3 pods served traffic and at least 99% succeeded), then does a rolling restart under load.
- **publish** (pushes to `main` only): builds and pushes both images to GHCR.

## Useful commands

```bash
kubectl -n bondcheck get pods -o wide                     # which node each replica runs on
kubectl -n bondcheck logs -l app.kubernetes.io/name=bondcheck-api --prefix -f
kubectl -n bondcheck scale deployment/bondcheck-api --replicas=6   # (the HPA will adjust it again)
kubectl -n bondcheck rollout restart deployment/bondcheck-api      # zero-downtime restart
kubectl -n bondcheck create job --from=cronjob/bondcheck-monitor monitor-now   # run the Monitor agent now
curl -si localhost:8080/backend/health | grep -i x-served-by       # which pod answered
```
