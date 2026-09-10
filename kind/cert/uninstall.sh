#!/bin/bash
set -euo pipefail

# Determine script directory
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

echo "==> Removing Let's Encrypt ClusterIssuer..."

if [ -f "$SCRIPT_DIR/le-cluster-issuer.yaml" ]; then
  kubectl delete -f "$SCRIPT_DIR/le-cluster-issuer.yaml" --ignore-not-found=true
else
  kubectl delete clusterissuer letsencrypt --ignore-not-found=true
fi

echo "==> Removing Cloudflare Secret..."
kubectl delete secret cloudflare-api-token -n cert-manager --ignore-not-found=true

echo "==> Uninstalling cert-manager Helm release..."
helm uninstall cert-manager -n cert-manager 2>/dev/null || true

echo "==> Deleting cert-manager namespace..."
kubectl delete namespace cert-manager --ignore-not-found=true

echo "==> Deleting cert-manager CRDs..."
kubectl get crd -o name | grep 'cert-manager.io' | xargs -r kubectl delete

echo "==> cert-manager uninstallation complete."