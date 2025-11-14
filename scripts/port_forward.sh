#!/usr/bin/env bash
# Expose an environment's gateway on localhost (works with every Minikube driver).
#   scripts/port_forward.sh [env] [local-port]
set -euo pipefail
ENV="${1:-dev}"
PORT="${2:-8080}"
CONTEXT="${KUBE_CONTEXT:-fleetsync}"
echo "Forwarding http://localhost:${PORT} -> svc/gateway in fleetsync-${ENV} (context ${CONTEXT})"
exec kubectl --context "${CONTEXT}" -n "fleetsync-${ENV}" port-forward svc/gateway "${PORT}:8080"
