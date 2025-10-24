#!/usr/bin/env sh
set -e
set -u

# This script is intended to run inside the bastion container defined in infra/local/external_workloads/docker-compose.yml
# It discovers LoadBalancer IPs for TF worker/ps services, ensures TensorFlow is installed,
# and launches the training coordinator that parallelizes across the K8s pods.

# Config
WORKER_SERVICES="tf-trainer-0 tf-trainer-1" # Add all the worker services
PS_SERVICE="tf-trainer-ps-0" # Add the Ps services
PORT=2222
# Default values for the environment variables
DATA_PATH=${DATA_PATH:-/data/health.csv}
OUTPUT_DIR=${OUTPUT_DIR:-/workloads/output/$(date +%Y%m%d_%H%M%S)}
EPOCHS=${EPOCHS:-10}
BATCH_SIZE=${BATCH_SIZE:-64}
CHIEF_PORT=${CHIEF_PORT:-2223} # TensorFlow coordinator gRPC port; the tf-bastion also called chief

# Determine a routable IPv4 for the coordinator (bastion). Respect CHIEF_ADDR if provided.
if [ -z "${CHIEF_ADDR:-}" ]; then # Check if the variable has not been set (not set or empty), then
                                  # execute the second if

  # Try to detect default IPv4 via routing table
  if command -v ip >/dev/null 2>&1; then # Check if the command ip is available
    # Using the ip V4 (-4) get the route to google dns, send error output to null, pipe the successfully output to awk
    # to iterate into the fields with length NF amd take the word after "src".
    CANDIDATE=$(ip -4 route get 8.8.8.8 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')
    # Check if the command return is none-empty (-n)
    if [ -n "$CANDIDATE" ]; then
      CHIEF_ADDR="$CANDIDATE"
    fi
  fi
fi
# In case of fail
if [ -z "${CHIEF_ADDR:-}" ]; then # If the variable was not set in the previous if-fi block
  # Fallback: hostname -I (capital i) and pick first IPv4 token
  if command -v hostname >/dev/null 2>&1; then # Check if the command is available
    for tok in $(hostname -I 2>/dev/null); do # Iterate all the ip addresses of the host (hostname -I)
                                              # and error output -> Null
      case "$tok" in
        *:*) ;; # Skip IPv6 tokens (ips matching ":")
        *.*) CHIEF_ADDR="$tok"; break ;; #  Is only required the fist ip V4  address, so, skip the rest.
      esac
    done
  fi
fi

# Final validation: must be IPv4, check not null or empty (True if empty or null) || the environment variable is an
# ip V6 (: instead . )
if [ -z "${CHIEF_ADDR:-}" ] || echo "$CHIEF_ADDR" | grep -q ":"; then
  echo "Unable to auto-detect a valid IPv4 CHIEF_ADDR. Set CHIEF_ADDR to an IPv4 reachable from K8s pods (e.g., 172.x/192.168.x)." >&2
  exit 4
fi

echo "Chief (coordinator) will advertise ${CHIEF_ADDR}:${CHIEF_PORT}"

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
if command -v python >/dev/null 2>&1; then # Error to std output
  PYTHON=python
elif command -v python3 >/dev/null 2>&1; then # Error to std output
  PYTHON=python3
else
  echo "Python is required inside bastion. Aborting." >&2 # Send to std error output
  exit 127
fi

mkdir -p "$OUTPUT_DIR"

# Ensure gRPC to chief bypasses proxies (avoid unexpected :443 redirection)
if [ -n "${no_proxy:-}" ]; then
  no_proxy="${no_proxy},${CHIEF_ADDR}"
else
  no_proxy="${CHIEF_ADDR}"
fi
if [ -n "${NO_PROXY:-}" ]; then
  NO_PROXY="${NO_PROXY},${CHIEF_ADDR}"
else
  NO_PROXY="${CHIEF_ADDR}"
fi
export no_proxy NO_PROXY

"$PYTHON" /workloads/raw-tf/train_tf_ps.py \
  --data-path "$DATA_PATH" \
  --output-dir "$OUTPUT_DIR" \
  --epochs "$EPOCHS" \
  --batch-size "$BATCH_SIZE" \
  --use-ps \
  --worker-replicas "$WORKER_COUNT" \
  --ps-replicas "$PS_COUNT" \
  --worker-addrs "$WORKER_ADDRS_CSV" \
  --ps-addrs "$PS_ADDRS_CSV" \
  --chief-addr "$CHIEF_ADDR" \
  --chief-port "$CHIEF_PORT"
