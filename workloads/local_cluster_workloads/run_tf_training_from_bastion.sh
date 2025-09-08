#!/usr/bin/env sh
set -eu

# This script is intended to run inside the bastion container defined in infra/local/external_workloads/docker-compose.yml
# It discovers LoadBalancer IPs for TF worker/ps services, ensures TensorFlow is installed,
# and launches the training coordinator that parallelizes across the K8s pods.

# Config
WORKER_SERVICES="tf-trainer-0 tf-trainer-1"
PS_SERVICE="tf-trainer-ps-0"
PORT=2222
DATA_PATH=${DATA_PATH:-/data/health.csv}
OUTPUT_DIR=${OUTPUT_DIR:-/workloads/output/$(date +%Y%m%d_%H%M%S)}
EPOCHS=${EPOCHS:-3}
BATCH_SIZE=${BATCH_SIZE:-64}

# Ensure kubectl available
if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required inside bastion to discover service IPs. Aborting." >&2
  exit 1
fi

# Resolve IPs from LoadBalancer services
get_lb_ip() {
  svc="$1"
  ip=$(kubectl get svc "$svc" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
  if [ -z "$ip" ]; then
    # Some environments set hostname instead of ip
    ip=$(kubectl get svc "$svc" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
  fi
  if [ -z "$ip" ]; then
    echo "Service $svc has no LoadBalancer IP/hostname assigned yet. Ensure MetalLB or an LB is configured." >&2
    exit 2
  fi
  echo "$ip"
}

WORKER_ADDRS_CSV=""
WORKER_COUNT=0
for svc in $WORKER_SERVICES; do
  ip=$(get_lb_ip "$svc")
  addr="${ip}:${PORT}"
  if [ -z "$WORKER_ADDRS_CSV" ]; then
    WORKER_ADDRS_CSV="$addr"
  else
    WORKER_ADDRS_CSV="$WORKER_ADDRS_CSV,$addr"
  fi
  WORKER_COUNT=$((WORKER_COUNT + 1))
  echo "Worker $svc -> $addr"
done

PS_IP=$(get_lb_ip "$PS_SERVICE")
PS_ADDRS_CSV="${PS_IP}:${PORT}"
PS_COUNT=1
echo "PS $PS_SERVICE -> ${PS_IP}:${PORT}"

# Ensure python exists; prefer python then python3
PYTHON=""
if command -v python >/dev/null 2>&1; then
  PYTHON=python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  echo "Python is required inside bastion. Aborting." >&2
  exit 3
fi

# Install TensorFlow if missing
if ! "$PYTHON" -c "import tensorflow as tf; print(tf.__version__)" >/dev/null 2>&1; then
  echo "Installing TensorFlow (CPU) inside bastion container..."
  "$PYTHON" -m pip install --no-cache-dir --upgrade pip >/dev/null 2>&1 || true
  "$PYTHON" -m pip install --no-cache-dir tensorflow >/dev/null
fi

mkdir -p "$OUTPUT_DIR"

"$PYTHON" /workloads/local_cluster_workloads/train_tf_ps.py \
  --data-path "$DATA_PATH" \
  --output-dir "$OUTPUT_DIR" \
  --epochs "$EPOCHS" \
  --batch-size "$BATCH_SIZE" \
  --use-ps \
  --worker-replicas "$WORKER_COUNT" \
  --ps-replicas "$PS_COUNT" \
  --worker-addrs "$WORKER_ADDRS_CSV" \
  --ps-addrs "$PS_ADDRS_CSV"
