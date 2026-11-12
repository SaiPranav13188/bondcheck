#!/usr/bin/env bash
# Fallback: tunnel the Envoy gateway to http://localhost:${LOCAL_PORT:-8080} with kubectl port-forward.
# Not needed for clusters made from k8s/kind-config.yaml, which map the gateway's NodePort to
# localhost:8080 directly. port-forward is a debugging tunnel: fine for browsing, not for load tests.
set -euo pipefail
LOCAL_PORT=${LOCAL_PORT:-8080}
SVC=$(kubectl get svc -n envoy-gateway-system \
  -l gateway.envoyproxy.io/owning-gateway-namespace=bondcheck,gateway.envoyproxy.io/owning-gateway-name=bondcheck \
  -o jsonpath='{.items[0].metadata.name}')
[ -n "$SVC" ] || { echo "gateway service not found; is the cluster up? (scripts/k8s-up.sh)"; exit 1; }
exec kubectl -n envoy-gateway-system port-forward "svc/$SVC" "$LOCAL_PORT:80"
