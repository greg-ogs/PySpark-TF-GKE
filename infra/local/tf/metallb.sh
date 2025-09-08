#!/usr/bin/env sh

kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.15.2/config/manifests/metallb-native.yaml

kubectl -n metallb-system wait deploy --all --for=condition=Available --timeout=120s

docker network inspect kind --format '{{json .IPAM.Config}}'

kubectl apply -f ./infra/local/tf/metallb-adreess-pool.yaml

# For the container kubectl using kind

# Powershell
#$src = "$env:USERPROFILE\.kube\config"
#$dst = "$env:USERPROFILE\.kube\config-kind-in-container"
#Copy-Item $src $dst -Force

#(Get-Content $dst) -replace 'https://127\.0\.0\.1:(\d+)', 'https://desktop-control-plane:$1' | Set-Content $dst

cp ~/.kube/config ~/.kube/config-kind-in-container
sed -i -E 's#https://127\.0\.0\.1:([0-9]+)#https://desktop-control-plane:\1#g' ~/.kube/config-kind-in-container
