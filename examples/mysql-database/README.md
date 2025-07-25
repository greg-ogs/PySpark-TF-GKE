# MySQL Database Statefulset
The actual MySQL database directory have the manifest for a distributed MySQL server in A single Kubernetes cluster.
> Multi node is not available yet.

> Taint is not available yet.

>[!WARNING]
> Security is not available yet.

## Testing the MySQL database
The workload is created using a temporal container.

**For Bash:**
```
kubectl run mysql-client --image=mysql:8.4.0 -i --rm --restart=Never --\
  mysql -h mysql-0.mysql <<EOF
CREATE DATABASE test;
CREATE TABLE test.messages (message VARCHAR(250));
INSERT INTO test.messages VALUES ('hello');
EOF
```

**And for Powershell:**
```
@"
CREATE DATABASE test;
CREATE TABLE test.messages (message VARCHAR(250));
INSERT INTO test.messages VALUES ('hello');
"@ | kubectl run mysql-client --image=mysql:8.4.0 -i --rm --restart=Never -- mysql -h mysql-0.mysql
```

Check the just created databea and table with:

**For Bash:**
```
kubectl run mysql-client --image=mysql:8.4.0 -i -t --rm --restart=Never --\
  mysql -h mysql-read -e "SELECT * FROM test.messages"
```

**And for Powershell:**
```
kubectl run mysql-client --image=mysql:8.4.0 -i -t --rm --restart=Never -- `
  mysql -h mysql-read -e "SELECT * FROM test.messages"
```

## Load a csv into a sql table
Run a forward port command to map port 3306 in the local cluster.
>[!WARNING]
> Only for local development, may differ in cloud providers. 
 
```
 kubectl port-forward svc/mysql-external 3306:3306
```