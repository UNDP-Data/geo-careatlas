#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

set -a
. "$SCRIPT_DIR/.env"
set +a

# Define exact variables to replace so it leaves everything else intact
VARS_TO_SUBST='$NAMESPACE $OAUTH_CLIENT_ID $OAUTH_CLIENT_SECRET $OAUTH_COOKIE_KEY $OAUTH_ORG_NAME $OAUTH_TEAM_NAME $OAUTH2_PROXY_COOKIE_DOMAINS $OAUTH2_PROXY_WHITELIST_DOMAINS'

envsubst "$VARS_TO_SUBST" < "$SCRIPT_DIR/values.yaml" > "$SCRIPT_DIR/rendered-values.yaml"

# Add & update Helm repo
helm repo add oauth2-proxy https://oauth2-proxy.github.io/manifests
helm repo update

echo "==> Deploying OAuth2-Proxy Helm release..."
#Deploy via Helm
helm upgrade --install github-oauth oauth2-proxy/oauth2-proxy \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  -f /$SCRIPT_DIR/rendered-values.yaml

rm /$SCRIPT_DIR/rendered-values.yaml
#aply auth route
kubectl apply -f $SCRIPT_DIR/auth-route.yaml

# Unset environment variables from current process memory
unset NAMESPACE \
      OAUTH_CLIENT_ID \
      OAUTH_CLIENT_SECRET \
      OAUTH_COOKIE_KEY \
      OAUTH_ORG_NAME \
      OAUTH_TEAM_NAME \
      OAUTH2_PROXY_COOKIE_DOMAINS \
      OAUTH2_PROXY_WHITELIST_DOMAINS \
      VARS_TO_SUBST


echo "==> oauth2-proxy installed successfully."

