#!/usr/bin/env bash
# Bring up BondCheck on a local multi-node Kubernetes cluster (kind), end to end:
#   kind cluster (1 control plane + 2 workers) -> metrics-server (for the HPA) -> Envoy Gateway
#   -> build + load images -> apply k8s/overlays/local -> wait for migrate/seed + rollouts
#   -> port-forward the gateway to http://localhost:8080
#
# Needs: docker, kind, kubectl, helm.   Usage: scripts/k8s-up.sh [--no-forward]
# Works from Git Bash on Windows, macOS and Linux.
set -euo pipefail

CLUSTER=bondcheck
NS=bondcheck
ENVOY_GATEWAY_VERSION=v1.9.3
METRICS_SERVER_CHART_VERSION=3.12.2
LOCAL_PORT=${LOCAL_PORT:-8080}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
for tool in docker kind kubectl helm; do
  command -v "$tool" >/dev/null || { echo "missing: $tool (see k8s/README.md)"; exit 1; }
done

step "Cluster"
if kind get clusters | grep -qx "$CLUSTER"; then
  echo "kind cluster '$CLUSTER' already exists"
else
  kind create cluster --config k8s/kind-config.yaml
fi
kubectl config use-context "kind-$CLUSTER" >/dev/null

step "metrics-server (CPU metrics for the HorizontalPodAutoscaler)"
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ >/dev/null 2>&1 || true
helm repo update metrics-server >/dev/null
helm upgrade --install metrics-server metrics-server/metrics-server -n kube-system \
  --version "$METRICS_SERVER_CHART_VERSION" --set 'args={--kubelet-insecure-tls}' --wait

step "Envoy Gateway $ENVOY_GATEWAY_VERSION (Gateway API controller)"
helm upgrade --install eg oci://docker.io/envoyproxy/gateway-helm --version "$ENVOY_GATEWAY_VERSION" \
  -n envoy-gateway-system --create-namespace --wait
kubectl wait --timeout=5m -n envoy-gateway-system deployment/envoy-gateway --for=condition=Available
kubectl apply -f k8s/cluster/

step "Build images"
docker build -t bondcheck-api:dev .
docker build -t bondcheck-frontend:dev frontend
kind load docker-image bondcheck-api:dev bondcheck-frontend:dev --name "$CLUSTER"

step "Deploy"
if [ ! -f k8s/overlays/local/secrets.env ]; then
  cp k8s/overlays/local/secrets.env.example k8s/overlays/local/secrets.env
  echo "created k8s/overlays/local/secrets.env from the example (edit it to add an ANTHROPIC_API_KEY)"
fi
# Jobs are immutable: replace the migrate Job on every deploy.
kubectl -n "$NS" delete job bondcheck-migrate --ignore-not-found >/dev/null 2>&1 || true
kubectl apply -k k8s/overlays/local
# Pods keep the same :dev tag across rebuilds, so restart them to pick up the new images.
kubectl -n "$NS" rollout restart deployment/bondcheck-api deployment/bondcheck-frontend >/dev/null

step "Wait for PostgreSQL, schema + demo seed, and rollouts"
kubectl -n "$NS" rollout status statefulset/postgres --timeout=5m
kubectl -n "$NS" wait job/bondcheck-migrate --for=condition=Complete --timeout=20m
kubectl -n "$NS" rollout status deployment/bondcheck-api --timeout=10m
kubectl -n "$NS" rollout status deployment/bondcheck-frontend --timeout=10m
# Wait for the routes to be accepted and Envoy's proxy pods to be up. (Not the Gateway's own Programmed
# condition: that also needs an external load-balancer IP, which kind/minikube never assign.)
kubectl -n "$NS" wait httproute/bondcheck-api httproute/bondcheck-frontend \
  --for=jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}'=True --timeout=5m
for i in $(seq 1 60); do
  kubectl -n envoy-gateway-system get deploy -l gateway.envoyproxy.io/owning-gateway-name=bondcheck \
    -o name 2>/dev/null | grep -q . && break
  sleep 2
done
kubectl -n envoy-gateway-system wait deploy -l gateway.envoyproxy.io/owning-gateway-name=bondcheck \
  --for=condition=Available --timeout=5m

kubectl -n "$NS" get pods -o wide
echo
kubectl -n "$NS" get hpa

if [ "${1:-}" = "--no-forward" ]; then exit 0; fi
step "Open http://localhost:$LOCAL_PORT  (API: http://localhost:$LOCAL_PORT/backend/health)  -- Ctrl+C to stop"
echo "In another terminal:  python scripts/loadtest.py      # see requests spread over the API pods"
exec "$ROOT/scripts/k8s-forward.sh"
