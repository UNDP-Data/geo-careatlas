#!/bin/bash

# Determine the directory where this script resides
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)"

# Source the .env file relative to the script directory
. "$SCRIPT_DIR/.env"


echo "==> Adding Jetstack Helm repository..."
helm repo add jetstack https://charts.jetstack.io
helm repo update

helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set crds.enabled=true \
  --set "extraArgs={--enable-gateway-api}"


echo "==> Creating Cloudflare API token Secret..."
kubectl create secret generic cloudflare-api-token \
  --namespace cert-manager \
  --from-literal=api-token="$CLOUDFLARE_API_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f "$SCRIPT_DIR/le-cluster-issuer.yaml"