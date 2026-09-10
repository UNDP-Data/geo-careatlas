#!/bin/bash
set -euo pipefail

DNS_ZONE="undpgeohub.org"

: "${DNS_ZONE:?DNS_ZONE must be defined in .env (e.g., undpgeohub.org)}"


TEST_SUBDOMAIN="test.${DNS_ZONE}"
CERT_NAME="test-${DNS_ZONE//./-}-cert"
SECRET_NAME="test-${DNS_ZONE//./-}-tls"



# Unconditional cleanup trap executed on normal exit, error, or Ctrl+C
cleanup() {
  echo ""
  echo "=================================================="
  echo "==> Cleaning up test resources unconditionally..."
  echo "=================================================="
  kubectl delete certificate "${CERT_NAME}" -n default --ignore-not-found=true
  kubectl delete secret "${SECRET_NAME}" -n default --ignore-not-found=true
  kubectl delete order -n default --all 2>/dev/null || true
  kubectl delete challenge -n default --all 2>/dev/null || true
  echo "[+] Test certificate and secrets removed."
}
trap cleanup EXIT



echo "=================================================="
echo "==> 1. Checking ClusterIssuer Health"
echo "=================================================="
if ! kubectl get clusterissuer letsencrypt >/dev/null 2>&1; then
  echo "[-] Error: ClusterIssuer 'letsencrypt' not found."
  exit 1
fi

ISSUER_READY=$(kubectl get clusterissuer letsencrypt -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
if [ "$ISSUER_READY" != "True" ]; then
  echo "[-] Warning: ClusterIssuer 'letsencrypt' is not Ready. Current status:"
  kubectl describe clusterissuer letsencrypt
  exit 1
fi
echo "[+] ClusterIssuer 'letsencrypt' is Ready."

echo ""
echo "=================================================="
echo "==> 2. Applying Certificate for ${TEST_SUBDOMAIN}"
echo "=================================================="
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: ${CERT_NAME}
  namespace: default
spec:
  secretName: ${SECRET_NAME}
  issuerRef:
    name: letsencrypt
    kind: ClusterIssuer
  dnsNames:
  - "${TEST_SUBDOMAIN}"
EOF

echo ""
echo "=================================================="
echo "==> 3. Waiting for DNS-01 Challenge & Issuance"
echo "=================================================="
echo "[*] Waiting up to 180s for Let's Encrypt validation..."

# Wait for cert-manager to mark the certificate as ready
if kubectl wait --namespace default \
  --for=condition=Ready certificate/"${CERT_NAME}" \
  --timeout=180s; then
  echo "[+] Certificate successfully issued!"
else
  echo "[-] Certificate failed to become ready within timeout. Debugging details:"
  echo "--- Challenges ---"
  kubectl get challenge -n default || true
  kubectl describe challenge -n default || true
  echo "--- Orders ---"
  kubectl get order -n default || true
  exit 1
fi

echo ""
echo "=================================================="
echo "==> 4. Inspecting Generated TLS Secret"
echo "=================================================="
if kubectl get secret "${SECRET_NAME}" -n default >/dev/null 2>&1; then
  echo "[+] Secret '${SECRET_NAME}' exists in namespace 'default'."
  echo ""
  echo "--- Certificate Subject, Issuer & Validity ---"
  kubectl get secret "${SECRET_NAME}" -n default -o jsonpath='{.data.tls\.crt}' | \
    base64 --decode | \
    openssl x509 -noout -issuer -subject -dates -ext subjectAltName
else
  echo "[-] Secret '${SECRET_NAME}' was not created."
  exit 1
fi

echo ""
echo "=================================================="
echo "==> Certificate Verification Completed Successfully"
echo "=================================================="