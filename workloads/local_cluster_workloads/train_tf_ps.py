import argparse
import csv
import io
import json
import os
import sys
import time
from typing import List, Tuple, Optional

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='google.protobuf.runtime_version')

import numpy as np
import tensorflow as tf
from urllib.request import urlopen


# ----------------------------
# Utility: Data loading
# ----------------------------

def _open_text(path_or_url: str) -> io.TextIOBase:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return io.TextIOWrapper(urlopen(path_or_url), encoding="utf-8")
    return open(path_or_url, "r", encoding="utf-8")


def load_health_csv(
    source: str,
    numeric_features: Optional[List[str]] = None,
    label_col: str = "subpopulation",
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Load CSV into memory using Python CSV module (keeps dependencies minimal).

    Returns: X (float32 numpy), y_idx (int32 numpy), label_vocab (list of str)
    """
    if numeric_features is None:
        numeric_features = ["value", "lower_ci", "upper_ci"]

    X: List[List[float]] = []
    y_raw: List[str] = []

    with _open_text(source) as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                label = row.get(label_col, "").strip()
                # Skip rows without label
                if not label:
                    continue
                # Parse numeric features; skip rows with missing/invalid
                feats = []
                ok = True
                for c in numeric_features:
                    v = row.get(c, "").strip()
                    if v == "" or v.lower() == "nan":
                        ok = False
                        break
                    feats.append(float(v))
                if not ok:
                    continue
                X.append(feats)
                y_raw.append(label)
            except Exception:
                # Skip malformed rows
                continue

    if not X:
        raise RuntimeError("No valid rows were parsed from the dataset.")

    # Build label vocabulary and index encode
    vocab = sorted(set(y_raw))
    index_map = {s: i for i, s in enumerate(vocab)}
    y_idx = np.array([index_map[s] for s in y_raw], dtype=np.int32)
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
    parser.add_argument("--data-path", default=os.environ.get("DATA_PATH", "infra/local/mysql-database/health.csv"), help="Path to CSV (when running on bastion/host)")
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
    if not os.path.exists(data_source):
        if args.data_url:
            data_source = args.data_url
        else:
            print(f"Data path {args.data_path} not found and no --data-url provided.", file=sys.stderr)
            sys.exit(2)

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
