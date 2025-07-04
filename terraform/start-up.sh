#!/bin/sh

apt-get update

apt-get install -y apt-transport-https ca-certificates gnupg curl

curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg

echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list

apt-get update && apt-get install -y google-cloud-cli

apt-get install -y google-cloud-cli-gke-gcloud-auth-plugin

apt-get install -y gke-gcloud-auth-plugin

apt-get install -y kubectl

apt-get install -y tar

apt-get install -y openjdk-17-jdk

# Install Python 3.11 and its development headers
apt-get install -y python3.11 \
                   python3.11-venv \
                   python3.11-dev

# Update alternatives to make python3 point to python3.11 (optional, but good for consistency)
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

apt-get install -y python3-pip

python3 -m pip install pyspark --break-system-packages

cat > commands.sh << 'EOF'
gcloud logging read "resource.type=k8s_node AND resource.labels.node_name=gke-ml-cluster-spark-pool-3b61dfe4-6v3w"
EOF
