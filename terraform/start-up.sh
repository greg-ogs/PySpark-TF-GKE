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

# Install java for spark server
apt-get install -y openjdk-17-jdk

# Install Python 3.11 and its development headers
apt-get install -y python3.11 \
                   python3.11-venv \
                   python3.11-dev

# Update alternatives to make python3 point to python3.11 (optional, but good for consistency)
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

#Install python pip
apt-get install -y python3-pip

# Install PySpark and required packages
python3 -m pip install pyspark numpy pandas google-cloud-storage --break-system-packages

# Get the project ID and set it as an environment variable
PROJECT_ID=$(gcloud config get-value project)
echo "export GCP_PROJECT_ID=${PROJECT_ID}" >> /etc/environment
echo "export GCP_PROJECT_ID=${PROJECT_ID}" >> /etc/profile.d/gcp-env.sh
chmod +x /etc/profile.d/gcp-env.sh

# Create a script to upload dataset to the GCS bucket
cat > /home/grego/upload_dataset.sh << 'EOF'
#!/bin/bash
# Get the project ID
PROJECT_ID=$(gcloud config get-value project)
BUCKET_NAME="${PROJECT_ID}-datasets"

# Change the health.csv dataset for the actual dataset.
gsutil cp health.csv gs://${BUCKET_NAME}/health.csv
EOF
chmod +x /home/grego/upload_dataset.sh

# Create a script to apply the ConfigMap with the correct project ID
cat > /home/grego/config.sh << 'EOF'
#!/bin/bash
# Get the project ID
PROJECT_ID=$(gcloud config get-value project)

# Replace the placeholder in the ConfigMap with the actual project ID
sed "s/\${PROJECT_ID}/$PROJECT_ID/g" gcp-config.yaml > gcp-config-applied.yaml
sed "s/\${PROJECT_ID}/$PROJECT_ID/g" spark-k8s-sa.yaml > spark-k8s-sa-applied.yaml

# Apply the ConfigMap
kubectl apply -f gcp-config-applied.yaml

# Apply the service account
kubectl apply -f spark-k8s-sa-applied.yaml

# The Google Service Account email
# The "ml-cluster-sa" must match with the tf output `service_account_email`.
GSA_EMAIL="ml-cluster-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Annotate the Kubernetes Service Account
# The spark-sa is the kubernetes (not google cloud) service account applied from the `spark-k8s-sa.yaml` manifest.
kubectl annotate serviceaccount spark-sa \
    --namespace default \
    iam.gke.io/gcp-service-account="${GSA_EMAIL}"


# Restart the Spark deployments to pick up the new service account
kubectl rollout restart deployment spark-master
kubectl rollout restart deployment spark-worker

EOF
chmod +x /home/grego/config.sh

