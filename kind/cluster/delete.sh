#!/bin/bash

# Determine the directory where this script resides
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Deleting KIND cluster: $CLUSTER_NAME..."
kind delete cluster --name care-cluster
