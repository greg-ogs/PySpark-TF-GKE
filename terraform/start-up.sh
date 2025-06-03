#!/bin/bash

apt-get update

apt-get install apt-transport-https ca-certificates gnupg curl

curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg

echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list

apt-get update && apt-get install google-cloud-cli

apt-get install google-cloud-cli-gke-gcloud-auth-plugin

apt-get install gke-gcloud-auth-plugin

apt-get install kubectl

cat > commands.sh << 'EOF'
gcloud logging read "resource.type=k8s_node AND resource.labels.node_name=gke-ml-cluster-spark-pool-3b61dfe4-6v3w"
EOF
