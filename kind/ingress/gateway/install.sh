#!/bin/bash

# Determine the directory where this script resides
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)"

# Source the .env file relative to the script directory
#. "$SCRIPT_DIR/.env"

# install KUBE Gateway API CRD
helm upgrade --install eg oci://docker.io/envoyproxy/gateway-helm \
  --version v1.2.0 \
  --namespace envoy-gateway-system \
  --create-namespace


