"""
A script for loading health dataset, building machine learning models, and managing distributed strategies.

This script includes utility functions for loading and processing health-related CSV files, creating
TensorFlow models, configuring distributed training strategies, and running the training workflow.
It uses the TensorFlow framework and its distributed capabilities for training models in parameter server or local
environments.

Modules:
--------
    - Data loading utilities.
    - Model building helpers.
    - Distributed strategy configuration and management.
    - Training logic implementation.

Imports:
--------
    argparse -> for arguments parsing from the sh startup script.

    typing -> For type annotations.


"""
import argparse
import csv
import io
import json
import os
import sys
from typing import List, Tuple, Optional

# TensorFlow-specific setting to reduce the amount of logging output, hiding INFO and WARNING
# and only showing ERROR.
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# Optional:
# suppresses a specific UserWarning that can arise from protobuf versions, cleaning up the console output.
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='google.protobuf.runtime_version')

import numpy as np
import tensorflow as tf
from urllib.request import urlopen


# ----------------------------
# Utility: Data loading
# ----------------------------

def _open_text(path_or_url: str) -> io.TextIOBase:
    """
    Opens a text file or retrieves text content from an HTTP/HTTPS URL and
    returns a readable text stream.
    If the input string starts with "http://"
    or "https://", the method assumes it's a URL and fetches the content using
    an HTTP request.
    Otherwise, it opens a local file with the specified path.
    Used inside the load_health_csv function.

    Params:
    -------

    path_or_url : str -> A string representing either a file path or a URL.

    return : io.TextIOBase -> A readable text stream from the local file or the remote resource.
    """
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return io.TextIOWrapper(urlopen(path_or_url), encoding="utf-8") # If is a URL, open it using HTTP request
    return open(path_or_url, "r", encoding="utf-8") # If is a local file, open it directly


def load_health_csv(
    source: str,
    numeric_features: Optional[List[str]] = None,
    label_col: str = "subpopulation",
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Load a CSV file into memory and parse it into a usable format.
    This function uses Python's CSV module to minimize dependencies and processes the data to return
    numeric features (X), label indices (y_idx), and the label vocabulary (label_vocab).
    It is specifically designed for health-related datasets, with default numeric features
    and a specific label column.
    Rows with missing or invalid data are skipped.

    Params:
    -------

    source : str -> Path to the source CSV file.

    numeric_features : Optional[List[str]] -> List of column names to parse as numeric features.
    Defaults:
        to ["value", "lower_ci", "upper_ci"] if not provided.

    label_col : str -> Name of the column to use for labels in the dataset.
    Defaults:
        to "subpopulation".

    :return: A tuple containing:
        - X (numpy.ndarray): Parsed numeric features as a float32 numpy array.
        - y_idx (numpy.ndarray): Label indices encoded as an int32 numpy array.
        - label_vocab (List[str]): A sorted list of unique label names.
    :rtype: Tuple[numpy.ndarray, numpy.ndarray, List[str]]
    """
    if numeric_features is None:
        numeric_features = ["value", "lower_ci", "upper_ci"] # Numeric features from example dataset (google health)

    X: List[List[float]] = []
    y_raw: List[str] = []

    with _open_text(source) as fh:
        reader = csv.DictReader(fh) # Read CSV as dicts
        for row in reader: # Iterate over rows in the CSV, each row is a dict with the header as keys.
            try:
                label = row.get(label_col, "").strip() # Get the label from the row for the label_col
                # (default: "subpopulation"), default to empty string if not found.
                if not label:
                    continue # Skip rows without a label in the subpopulation column.

                # Parse numeric features; skip rows with missing/invalid
                feats = [] # Auxiliar list to store numeric features for this row.
                ok = True # Flag to indicate if the row is valid.
                for c in numeric_features: # Iterate over the numeric features.
                    v = row.get(c, "").strip() # Get the value for the current feature.
                    if v == "" or v.lower() == "nan":
                        ok = False
                        break # Skip rows with any missing or invalid numeric feature values
                    feats.append(float(v))
                if not ok:
                    continue # If any of the numeric features are invalid, skip the row and don't add it to X or y_raw
                X.append(feats)
                y_raw.append(label)
            except Exception:
                # Skip malformed rows
                continue

    if not X:
        raise RuntimeError("No valid rows were parsed from the dataset.")

    # Build label vocabulary and index encode
    vocab = sorted(set(y_raw)) # Use set to remove duplicates and sort for determinism.
    index_map = {s: i for i, s in enumerate(vocab)} # Dict to map unique labels to indices.
    y_idx = np.array([index_map[s] for s in y_raw], dtype=np.int32) # Iterates over y_raw and uses index_map to encode
    # the labels. Each value in y_raw (s) is mapped to the corresponding index_map[s].
    X_arr = np.asarray(X, dtype=np.float32)

    return X_arr, y_idx, vocab


# ----------------------------
# Model building
# ----------------------------

def build_sequential_model(input_dim: int, num_classes: int) -> tf.keras.Model:
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(input_dim,)),
            tf.keras.layers.Dense(64, activation="relu"),
            tf.keras.layers.Dense(32, activation="relu"),
            tf.keras.layers.Dense(num_classes, activation="softmax"),
        ]
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        metrics=["accuracy"],
    )
    return model


# ----------------------------
# Distributed strategy helpers
# ----------------------------

def build_cluster_def(worker_replicas: int, ps_replicas: int, port: int, worker_addrs: Optional[List[str]] = None, ps_addrs: Optional[List[str]] = None, chief_addr: Optional[str] = None, chief_port: int = 2223) -> dict:
    # If explicit addresses provided (e.g., from bastion via LoadBalancer IPs), use them
    if worker_addrs:
        workers = worker_addrs
    else:
        workers = [f"tf-trainer-{i}.tf-trainer-worker-headless:{port}" for i in range(worker_replicas)]
    cluster_def = {"worker": workers}
    if ps_replicas > 0:
        if ps_addrs:
            ps = ps_addrs
        else:
            ps = [f"tf-trainer-ps-{i}.tf-trainer-ps-headless:{port}" for i in range(ps_replicas)]
        cluster_def["ps"] = ps
    # Include chief if provided (must be routable from the K8s pods)
    if chief_addr:
        cluster_def["chief"] = [f"{chief_addr}:{chief_port}"]
    return cluster_def


def make_parameter_server_strategy(worker_replicas: int, ps_replicas: int, port: int = 2222, worker_addrs: Optional[List[str]] = None, ps_addrs: Optional[List[str]] = None, chief_addr: Optional[str] = None, chief_port: int = 2223) -> tf.distribute.ParameterServerStrategy:
    cluster_def = build_cluster_def(worker_replicas, ps_replicas, port, worker_addrs, ps_addrs, chief_addr, chief_port)
    print("Computed ClusterSpec:", json.dumps(cluster_def), flush=True)

    # Basic validation and sanitization for chief address to avoid IPv6 and malformed inputs
    if chief_addr:
        # Reject IPv6 literals or bracketed addresses and any scheme prefixes
        if ":" in chief_addr and "." not in chief_addr:
            raise RuntimeError(
                f"chief_addr appears to be IPv6 ('{chief_addr}'). Please provide an IPv4 address reachable from K8s pods."
            )
        if any(sym in chief_addr for sym in ["/", "[", "]", " "]):
            raise RuntimeError(
                f"chief_addr '{chief_addr}' is malformed. Provide a raw IPv4 like 192.168.1.10 without scheme or brackets."
            )
        # Optional strict IPv4 check
        parts = chief_addr.split(".")
        if len(parts) != 4 or any(not p.isdigit() or not (0 <= int(p) <= 255) for p in parts):
            raise RuntimeError(
                f"chief_addr '{chief_addr}' is not a valid IPv4 address."
            )

    # If a chief address is provided, declare this process as chief via TF_CONFIG
    if chief_addr:
        tf_config = {
            "cluster": cluster_def,
            "task": {"type": "chief", "index": 0},
        }
        os.environ["TF_CONFIG"] = json.dumps(tf_config)
        print("TF_CONFIG set:", os.environ["TF_CONFIG"], flush=True)

    resolver = tf.distribute.cluster_resolver.SimpleClusterResolver(
        cluster_spec=tf.train.ClusterSpec(cluster_def),
        rpc_layer="grpc",
    )
    variable_partitioner = tf.distribute.experimental.partitioners.MinSizePartitioner(
        min_shard_bytes=256 << 10, max_shards=max(ps_replicas, 1)
    )
    strategy = tf.distribute.ParameterServerStrategy(
        cluster_resolver=resolver, variable_partitioner=variable_partitioner
    )
    return strategy


# ----------------------------
# Training logic
# ----------------------------

def run_training(
    data_source: str,
    output_dir: str,
    epochs: int,
    batch_size: int,
    use_parameter_server: bool,
    worker_replicas: int,
    ps_replicas: int,
    port: int = 2222,
    worker_addrs: Optional[List[str]] = None,
    ps_addrs: Optional[List[str]] = None,
    chief_addr: Optional[str] = None,
    chief_port: int = 2223,
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    print(f"Loading dataset from: {data_source}")
    X, y, label_vocab = load_health_csv(data_source)
    num_classes = int(np.max(y)) + 1
    input_dim = X.shape[1]

    # Save label map
    with open(os.path.join(output_dir, "label_map.json"), "w", encoding="utf-8") as fh:
        json.dump({int(i): s for i, s in enumerate(label_vocab)}, fh, ensure_ascii=False, indent=2)

    # Build dataset
    ds = tf.data.Dataset.from_tensor_slices((X, y))
    # Shuffle with a modest buffer to avoid huge memory in coordinator
    ds = ds.shuffle(buffer_size=min(10000, len(X))).batch(batch_size).repeat()

    steps_per_epoch = max(1, len(X) // batch_size)

    if use_parameter_server and (worker_replicas > 0):
        print("Using ParameterServerStrategy with workers and ps.")
        if worker_addrs:
            print("Worker addrs:", worker_addrs)
        if ps_addrs:
            print("PS addrs:", ps_addrs)
        strategy = make_parameter_server_strategy(worker_replicas, ps_replicas, port, worker_addrs, ps_addrs, chief_addr, chief_port)

        # Switch to ClusterCoordinator-based custom training loop (DatasetCreator removed)
        def per_worker_dataset_fn(input_context: Optional[tf.distribute.InputContext] = None):
            local_ds = tf.data.Dataset.from_tensor_slices((X, y))
            if input_context is not None:
                local_ds = local_ds.shard(input_context.num_input_pipelines, input_context.input_pipeline_id)
            local_ds = local_ds.shuffle(buffer_size=min(10000, len(X))).batch(batch_size).repeat()
            return local_ds

        with strategy.scope():
            model = build_sequential_model(input_dim, num_classes)
            # Build losses/optimizer/metrics explicitly for custom loop
            optimizer = tf.keras.optimizers.Adam(learning_rate=1e-3)
            loss_obj = tf.keras.losses.SparseCategoricalCrossentropy()
            train_acc = tf.keras.metrics.SparseCategoricalAccuracy()
            train_loss = tf.keras.metrics.Mean()

        # Create a ClusterCoordinator to drive training from the chief/coordinator process
        coordinator = tf.distribute.coordinator.ClusterCoordinator(strategy)
        per_worker_ds = coordinator.create_per_worker_dataset(per_worker_dataset_fn)
        per_worker_iter = iter(per_worker_ds)

        @tf.function
        def per_worker_train_step(iterator):
            def step_fn(inputs):
                features, labels = inputs
                with tf.GradientTape() as tape:
                    logits = model(features, training=True)
                    loss = loss_obj(labels, logits)
                    # Add possible regularization losses
                    loss += tf.add_n(model.losses) if model.losses else 0.0
                grads = tape.gradient(loss, model.trainable_variables)
                optimizer.apply_gradients(zip(grads, model.trainable_variables))
                train_acc.update_state(labels, logits)
                train_loss.update_state(loss)
                return loss

            return strategy.run(step_fn, args=(next(iterator),))

        # Training loop
        for epoch in range(epochs):
            print(f"Starting epoch {epoch+1}/{epochs}...")
            train_acc.reset_state()
            train_loss.reset_state()

            # Schedule one step per required step_per_epoch; wait for completion
            futures = []
            for _ in range(steps_per_epoch):
                f = coordinator.schedule(per_worker_train_step, args=(per_worker_iter,))
                futures.append(f)
            # Block until all scheduled steps finish
            coordinator.join()

            print(f"Epoch {epoch+1} - loss: {train_loss.result().numpy():.4f} - accuracy: {train_acc.result().numpy():.4f}")

        # Mimic Keras History-like output for downstream logging
        history = type("_H", (), {"history": {"accuracy": [train_acc.result().numpy()]}})()
    else:
        print("Running single-process (no distributed strategy).")
        model = build_sequential_model(input_dim, num_classes)
        history = model.fit(ds, epochs=epochs, steps_per_epoch=steps_per_epoch)

    # Save model
    save_path = os.path.join(output_dir, "model.keras")
    model.save(save_path)
    print(f"Model saved to: {save_path}")

    # Log final metrics
    final_acc = history.history.get("accuracy", [None])[-1]
    print(f"Final training accuracy: {final_acc}")


def parse_args(argv: List[str]):
    parser = argparse.ArgumentParser(description="Train TF Keras model on health.csv with optional ParameterServerStrategy")
    parser.add_argument("--data-path", default=os.environ.get("DATA_PATH", "/app/infra/local/mysql-database/datasets/csvs/health.csv"), help="Path to CSV (when running on bastion/host)")
    parser.add_argument("--data-url", default=os.environ.get("DATA_URL", ""), help="HTTP(S) URL to CSV (used inside cluster if path not mounted)")
    parser.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", "./tf-model"))
    parser.add_argument("--epochs", type=int, default=int(os.environ.get("EPOCHS", "3")))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("BATCH_SIZE", "64")))
    parser.add_argument("--use-ps", action="store_true", help="Enable ParameterServerStrategy coordinator mode")
    parser.add_argument("--worker-replicas", type=int, default=int(os.environ.get("WORKER_REPLICAS", "2")))
    parser.add_argument("--ps-replicas", type=int, default=int(os.environ.get("PS_REPLICAS", "1")))
    parser.add_argument("--port", type=int, default=int(os.environ.get("TF_GRPC_PORT", "2222")))
    parser.add_argument("--worker-addrs", default=os.environ.get("WORKER_ADDRS", ""), help="Comma-separated worker addresses (host:port) when running outside cluster")
    parser.add_argument("--ps-addrs", default=os.environ.get("PS_ADDRS", ""), help="Comma-separated ps addresses (host:port) when running outside cluster")
    parser.add_argument("--chief-addr", default=os.environ.get("CHIEF_ADDR", ""), help="Routable IPv4 address of the coordinator (bastion) accessible from K8s pods")
    parser.add_argument("--chief-port", type=int, default=int(os.environ.get("CHIEF_PORT", "2223")), help="Coordinator gRPC port (exposed on tf-bastion)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    input("Press enter to continue...")
    # Resolve data source: prefer local path; if not existent and data-url provided -> use URL
    data_source = args.data_path

    worker_addrs = [s.strip() for s in args.worker_addrs.split(",") if s.strip()] if args.worker_addrs else None
    ps_addrs = [s.strip() for s in args.ps_addrs.split(",") if s.strip()] if args.ps_addrs else None

    run_training(
        data_source=data_source,
        output_dir=args.output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        use_parameter_server=args.use_ps,
        worker_replicas=args.worker_replicas,
        ps_replicas=args.ps_replicas,
        port=args.port,
        worker_addrs=worker_addrs,
        ps_addrs=ps_addrs,
        chief_addr=(args.chief_addr if args.chief_addr else None),
        chief_port=args.chief_port,
    )
