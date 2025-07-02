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

cat > commands.sh << 'EOF'
gcloud logging read "resource.type=k8s_node AND resource.labels.node_name=gke-ml-cluster-spark-pool-3b61dfe4-6v3w"
EOF
