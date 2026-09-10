#!/bin/bash

# Determine the directory where this script resides
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the .env file relative to the script directory
. "$SCRIPT_DIR/.env"

# Create cluster using the config relative to the script directory
kind create cluster --name care-cluster --config "$SCRIPT_DIR/cluster.yaml"