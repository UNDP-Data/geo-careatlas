#!/bin/bash

# Determine the directory where this script resides
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)"

# Source the .env file relative to the script directory
. "$SCRIPT_DIR/.env"

# Stop all containers belonging to the cluster
docker start $(docker ps -aq --filter "name=care-cluster")