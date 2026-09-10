#!/bin/bash

# Determine the directory where this script resides
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)"

kubectl delete httproute --all --all-namespaces
kubectl delete gateway --all --all-namespaces

echo "Deleting ingress..."
helm uninstall eg -n envoy-gateway-system 2>/dev/null || true

# Delete Envoy Gateway CRDs if they exist
ENVOY_CRDS=$(kubectl get crd -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep 'gateway.envoyproxy.io')
if [ -n "$ENVOY_CRDS" ]; then
  echo "$ENVOY_CRDS" | xargs kubectl delete crd
fi

# Delete standard Gateway API CRDs if they exist
GW_CRDS=$(kubectl get crd -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep 'gateway.networking.k8s.io')
if [ -n "$GW_CRDS" ]; then
  echo "$GW_CRDS" | xargs kubectl delete crd
fi

# Remove namespace
kubectl delete namespace envoy-gateway-system --ignore-not-found=true
