#!/usr/bin/env bash
# Expose the Envoy gateway of the BondCheck cluster on http://localhost:${LOCAL_PORT:-8080}.
# (kind has no cloud load balancer; on a real cloud the Gateway gets an external IP instead.)
set -euo pipefail
LOCAL_PORT=${LOCAL_PORT:-8080}
SVC=$(kubectl get svc -n envoy-gateway-system \
  -l gateway.envoyproxy.io/owning-gateway-namespace=bondcheck,gateway.envoyproxy.io/owning-gateway-name=bondcheck \
  -o jsonpath='{.items[0].metadata.name}')
[ -n "$SVC" ] || { echo "gateway service not found; is the cluster up? (scripts/k8s-up.sh)"; exit 1; }
exec kubectl -n envoy-gateway-system port-forward "svc/$SVC" "$LOCAL_PORT:80"
