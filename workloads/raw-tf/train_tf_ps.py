"""
A script for loading a dataset, building machine learning models, and managing distributed strategies.

This script includes utility functions for loading and processing CSV files or image datasets, creating
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
import datetime
import io
import json
import os
import sys
from typing import List, Tuple, Optional

import matplotlib.pyplot as plt

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


# ----------------------------------------------------------------------------------------------------------------------
# Utility: CSV data helpers (load)
# ----------------------------------------------------------------------------------------------------------------------

def open_text(path_or_url: str) -> io.TextIOBase:
    """
    Opens a text file or retrieves text content from an HTTP/HTTPS URL and
    returns a readable text stream.
    If the input string starts with "http://"
    or "https://", the method assumes it's a URL and fetches the content using
    an HTTP request.
    Otherwise, it opens a local file with the specified path.
    Used inside the load_csv function.

    Params:
    -------

    path_or_url : str -> A string representing either a file path or a URL.

    return : io.TextIOBase -> A readable text stream from the local file or the remote resource.
    """
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return io.TextIOWrapper(urlopen(path_or_url), encoding="utf-8") # If is a URL, open it using HTTP request
    return open(path_or_url, "r", encoding="utf-8") # If is a local file, open it directly


def load_csv(
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

    with open_text(source) as fh:
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

# ----------------------------------------------------------------------------------------------------------------------
# Utility: Image dataset helpers (load)
# ----------------------------------------------------------------------------------------------------------------------

def list_image_classes(data_dir: str) -> List[str]:
    """
    Deprecated: Folder-per-class image structure is no longer supported.

    This project now expects a flat directory of images with a clean_labels.jsonl file
    providing pixel coordinates for each image. This function is kept for
    backward compatibility but will always raise to prevent accidental use.
    """
    raise RuntimeError(
        "Folder-per-class structure is no longer supported. Use clean_labels.jsonl with a flat image directory."
    )


def count_images(data_dir: str) -> int:
    """
    Count labeled images using clean_labels.jsonl in a flat directory.

    Only counts entries that both exist on disk and have a supported image
    extension.
    """
    labels_path = os.path.join(data_dir, "clean_labels.jsonl")
    if not os.path.isfile(labels_path):
        raise RuntimeError(f"clean_labels.jsonl not found in: {data_dir}")
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".ppm"}
    total = 0
    with open(labels_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            name = str(obj.get("image", "")).strip()
            if not name:
                continue
            _, ext = os.path.splitext(name.lower())
            if ext not in exts:
                continue
            if os.path.isfile(os.path.join(data_dir, name)):
                total += 1
    if total == 0:
        raise RuntimeError("No labeled images found (clean_labels.jsonl present but matched zero files).")
    return total


def make_image_dataset(
        data_dir: str,
        image_size: Tuple[int, int],
        batch_size: int,
        shuffle: bool = True,
        input_context: Optional[tf.distribute.InputContext] = None,
) -> tf.data.Dataset:
    """
    Create a tf.data.Dataset for regression on (x_px, y_px) from a flat folder of images
    and a clean_labels.jsonl file.

    - clean_labels.jsonl format (per line):
      {"image": "<file>", "point": {"x_px": <float>, "y_px": <float>},
       "image_size": {"width": <int>, "height": <int>}}

    Targets are automatically scaled from original pixel coordinates to the
    provided resized image_size so the model predicts pixels in the resized
    space (not normalized). This keeps the target in pixels as requested while
    matching the actual tensor shape given to the model.
    """
    labels_path = os.path.join(data_dir, "clean_labels.jsonl")
    if not os.path.isfile(labels_path):
        raise RuntimeError(f"clean_labels.jsonl not found in: {data_dir}")

    img_h, img_w = int(image_size[0]), int(image_size[1])

    filepaths: List[str] = []
    targets: List[List[float]] = []

    exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".ppm"}
    with open(labels_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            name = str(obj.get("image", "")).strip()
            if not name:
                continue
            _, ext = os.path.splitext(name.lower())
            if ext not in exts:
                continue
            full_path = os.path.join(data_dir, name)
            if not os.path.isfile(full_path):
                continue

            point = obj.get("point") or {}
            x_px = point.get("x_px")
            y_px = point.get("y_px")
            if x_px is None or y_px is None:
                continue

            # Is not required because no matter what, the output must be the pixel in original size
            # img_size = obj.get("image_size") or {}
            # ow = img_size.get("width")
            # oh = img_size.get("height")
            # # If original sizes are missing, fall back to assuming the same as resize
            # if not ow or not oh:
            #     ow, oh = img_w, img_h
            #
            # # Scale pixel coordinates from original image space to the resized space
            # sx = float(img_w) / float(ow)
            # sy = float(img_h) / float(oh)
            # tx = float(x_px) * sx
            # ty = float(y_px) * sy

            filepaths.append(full_path)
            targets.append([x_px, y_px])

    if not filepaths:
        raise RuntimeError("No valid labeled images were parsed from clean_labels.jsonl")

    # Optionally shuffle at the file list level for better randomness pre-epoch
    if shuffle:
        rng = np.random.default_rng(1337)
        idx = np.arange(len(filepaths))
        rng.shuffle(idx)
        filepaths = [filepaths[i] for i in idx]
        targets = [targets[i] for i in idx]

    fp_ds = tf.data.Dataset.from_tensor_slices(filepaths)
    y_ds = tf.data.Dataset.from_tensor_slices(tf.convert_to_tensor(targets, dtype=tf.float32))
    ds = tf.data.Dataset.zip((fp_ds, y_ds))

    def _load_and_preprocess(path, y):
        img = tf.io.read_file(path)
        img = tf.image.decode_image(img, channels=3, expand_animations=False)
        img = tf.image.resize(img, [img_h, img_w])
        img = tf.cast(img, tf.float32) / 255.0
        return img, y

    # Prioritize parallel processing for speed instead of RAM usage, tf.data.AUTOTUNE,
    # set autotune to a hardcoded number to void RAM overflow.
    ds = ds.map(_load_and_preprocess, num_parallel_calls=tf.data.AUTOTUNE)

    if input_context is not None:
        ds = ds.shard(input_context.num_input_pipelines, input_context.input_pipeline_id)

    if shuffle:
        ds = ds.shuffle(buffer_size=min(3000, len(filepaths)))

    # Prioritize parallel processing for speed instead of RAM usage, tf.data.AUTOTUNE
    # set autotune to a hardcoded number to void RAM overflow.
    ds = ds.batch(batch_size).repeat().prefetch(1)
    return ds

# ----------------------------
# Model building
# ----------------------------

def build_deep_model(input_dim: int, num_classes: int) -> tf.keras.Model:
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(input_dim,)),
            tf.keras.layers.Dense(16, activation="relu"),
            tf.keras.layers.Dense(32, activation="relu"),
            tf.keras.layers.Dense(64, activation="relu"),
            tf.keras.layers.Dense(num_classes, activation="softmax"), # Softmax because multiclass classification
        ]
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        metrics=["accuracy"],
    )
    return model


def build_cnn_model(input_shape: Tuple[int, int, int], num_outputs: int = 2, flat: bool = False) -> tf.keras.Model:
    """Build a CNN regressor that predicts (x_px, y_px) in resized pixels."""
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=input_shape),
            tf.keras.layers.Conv2D(8, 5, padding="same"),
            tf.keras.layers.PReLU(),
            tf.keras.layers.MaxPooling2D(),
            tf.keras.layers.Conv2D(16, 5, padding="same"),
            tf.keras.layers.PReLU(),
            tf.keras.layers.MaxPooling2D(),
            tf.keras.layers.Conv2D(32, 5, padding="same"),
            tf.keras.layers.PReLU(),
            tf.keras.layers.MaxPooling2D(),
            tf.keras.layers.Conv2D(64, 5, padding="same"),
            tf.keras.layers.PReLU(),
            tf.keras.layers.MaxPooling2D(),
            tf.keras.layers.Conv2D(64, 5, padding="same"),
            tf.keras.layers.PReLU(),
            tf.keras.layers.Flatten() if flat else tf.keras.layers.GlobalAveragePooling2D(),
            tf.keras.layers.Dense(2048, activation="relu") if flat else tf.keras.layers.Dense(128, activation="relu"),
            tf.keras.layers.Dense(num_outputs, activation="linear"),
        ]
    )

    model.summary()

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss=tf.keras.losses.MeanSquaredError(),
        metrics=[tf.keras.metrics.MeanAbsoluteError(name="mae"), tf.keras.metrics.MeanSquaredError(name="mse")],
    )
    return model


# ----------------------------
# Distributed strategy helpers
# ----------------------------

def build_cluster_def(worker_replicas: int, ps_replicas: int, port: int, worker_addrs: Optional[List[str]] = None,
                      ps_addrs: Optional[List[str]] = None, chief_addr: Optional[str] = None,
                      chief_port: int = 2223) -> dict:
    """
    Builds and returns a TensorFlow cluster definition based on the number of worker replicas,
    parameter server replicas, and chief address (if provided).

    If no explicit addresses are provided, default Kubernetes headless service naming conventions
    are used to generate the respective addresses.
    This allows the creation of a valid cluster configuration for distributed TensorFlow training.

    Params:
    -------
    worker_replicas : int -> The number of worker replicas in the cluster.

    ps_replicas : int -> The number of parameter server replicas in the cluster.

    port : int -> The port used by the workers and parameter servers for communication.

    worker_addrs : Optional[List[str]] -> A list of explicit addresses for the worker nodes. Default is None.

    ps_addrs : Optional[List[str]] -> A list of explicit addresses for the parameter server nodes. Default is None.

    chief_addr : Optional[str] -> An explicit address for the chief node. Default is None.

    chief_port : int -> The port used by the chief node for communication. Default is 2223.

    :return : dict -> A dictionary defining the cluster structure, containing address mappings for
        worker nodes, parameter servers, and the chief if provided.

    """

    # If explicit addresses provided (e.g., from bastion via LoadBalancer IPs), use them
    if worker_addrs:
        workers = worker_addrs
    else:
        # In case of no worker's argument is provided, use the default headless service name
        workers = [f"tf-trainer-{i}.tf-trainer-worker-headless:{port}" for i in range(worker_replicas)]
    # define a role for the workers
    cluster_def = {"worker": workers}
    # Now is the same for the parameter servers pods
    if ps_replicas > 0:
        if ps_addrs:
            ps = ps_addrs
        else:
            ps = [f"tf-trainer-ps-{i}.tf-trainer-ps-headless:{port}" for i in range(ps_replicas)]
        # define role for the parameter servers
        cluster_def["ps"] = ps

    # Include chief if provided (must be routable from the K8s pods), check the run_tf_training_from_bastion.sh script.
    if chief_addr:
        cluster_def["chief"] = [f"{chief_addr}:{chief_port}"]
    return cluster_def


def make_parameter_server_strategy(worker_replicas: int, ps_replicas: int, port: int = 2222,
                                   worker_addrs: Optional[List[str]] = None, ps_addrs: Optional[List[str]] = None,
                                   chief_addr: Optional[str] = None,
                                   chief_port: int = 2223) -> tf.distribute.ParameterServerStrategy:
    """
    Creates and configures a TensorFlow Parameter Server Strategy.

    This function sets up a distributed training strategy using `tf.distribute.ParameterServerStrategy`.
    It builds a cluster definition based on the provided number of worker and parameter
    server replicas, network addresses, and chief address/port. Basic validation is applied to ensure
    the provided chief address is a valid and appropriate IPv4 address without unwanted schemes, brackets,
    or malformed formats. If a chief address is provided, a corresponding `TF_CONFIG` environment variable
    is set up to indicate that this process is running as the chief.

    Params:
    -------

    worker_replicas : int -> Number of worker replicas in the cluster. Must be an integer.
    ps_replicas : int -> Number of parameter server replicas in the cluster. Must be an integer.
    port : int -> Default port number to use for worker and parameter server addresses. Defaults to 2222.
    worker_addrs : Optional[List[str]] -> List of IPv4 addresses corresponding to the workers. If not provided, defaults to None.
    ps_addrs : Optional[List[str]] -> List of IPv4 addresses corresponding to the parameter servers. If not provided, defaults to None.
    chief_addr : Optional[str] -> IPv4 address of the chief server. Must be a valid and reachable IPv4 address. Defaults to None.
    chief_port : int -> Default port number for the chief server. Defaults to 2223.

    :return : tf.distribute.ParameterServerStrategy -> A `tf.distribute.ParameterServerStrategy` configured for distributed training.

    """

    # Build cluster definition based on provided addresses and replica counts
    cluster_def = build_cluster_def(worker_replicas, ps_replicas, port, worker_addrs, ps_addrs, chief_addr, chief_port)
    print("Computed ClusterSpec:", json.dumps(cluster_def), flush=True) # print cluster definition inmediately

    # Basic validation and sanitization for the chief address to avoid IPv6 and malformed inputs
    if chief_addr:
        # Reject IPv6 literals or bracketed addresses and any scheme prefixes
        if ":" in chief_addr and "." not in chief_addr:
            raise RuntimeError(
                f"chief_addr appears to be IPv6 ('{chief_addr}'). Please provide an IPv4 address reachable from K8s pods."
            )
        # Creates an iterable for any function to check if any of the symbols are in the string
        if any(sym in chief_addr for sym in ["/", "[", "]", " "]):
            raise RuntimeError(
                f"chief_addr '{chief_addr}' is malformed. Provide a raw IPv4 like 192.168.1.10 without scheme or brackets."
            )
        # Strict IPv4 check
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

def run_deep_training(
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
    """
    Executes the training pipeline for a machine learning model, supporting both
    single-machine and distributed strategies, including parameter server
    orchestrated training. It preprocesses the dataset, builds the model, trains
    it over specified epochs, and saves the resultant model along with a label
    mapping file.

    :param data_source: Path to the input dataset (CSV format) containing features
        and labels for training.
    :type data_source: str
    :param output_dir: Directory where output artifacts, including the model and
        label map, are saved.
    :type output_dir: str
    :param epochs: The number of epochs the training process will iterate.
    :type epochs: int
    :param batch_size: Number of samples processed per training batch.
    :type batch_size: int
    :param use_parameter_server: Specifies whether distributed training with
        parameter servers is utilized.
    :type use_parameter_server: bool
    :param worker_replicas: Number of worker replicas used in distributed
        training.
    :type worker_replicas: int
    :param ps_replicas: Number of parameter server replicas used in distribution
        training.
    :type ps_replicas: int
    :param port: Default port used for communication in distributed training
        (e.g., workers and parameter servers).
    :type port: int
    :param worker_addrs: List of addresses for worker nodes in distributed
        training.
    :type worker_addrs: Optional[List[str]]
    :param ps_addrs: List of addresses for parameter servers in distributed
        training.
    :type ps_addrs: Optional[List[str]]
    :param chief_addr: Address of the chief node (coordinator) in distributed
        training.
    :type chief_addr: Optional[str]
    :param chief_port: Default port used for the chief node communication during
        distributed training.
    :type chief_port: int
    :return: None
    """
    os.makedirs(output_dir, exist_ok=True)

    print(f"Loading dataset from: {data_source}")
    X, y, label_vocab = load_csv(data_source)
    num_classes = int(np.max(y)) + 1
    input_dim = X.shape[1]

    # Save label map
    with open(os.path.join(output_dir, "label_map.json"), "w", encoding="utf-8") as fh:
        json.dump({int(i): s for i, s in enumerate(label_vocab)}, fh, ensure_ascii=False, indent=2)

    steps_per_epoch = max(1, len(X) // batch_size)

    if use_parameter_server and (worker_replicas > 0): # Environment variable to select if ps strategy is applied
        print("Using ParameterServerStrategy with workers and ps.")
        if worker_addrs:
            print("Worker addrs:", worker_addrs)
        if ps_addrs:
            print("PS addrs:", ps_addrs)
        strategy = make_parameter_server_strategy(worker_replicas, ps_replicas, port, worker_addrs, ps_addrs, chief_addr, chief_port)

        # Dataset per worker function (for parameter server strategy and coordinator mode)
        def per_worker_dataset_fn(input_context: Optional[tf.distribute.InputContext] = None):
            local_ds = tf.data.Dataset.from_tensor_slices((X, y))
            if input_context is not None:
                local_ds = local_ds.shard(input_context.num_input_pipelines, input_context.input_pipeline_id)
            local_ds = local_ds.shuffle(buffer_size=min(3000, len(X))).batch(batch_size).repeat()
            return local_ds

        with strategy.scope():
            model = build_deep_model(input_dim, num_classes)
            # Build losses/optimizer/metrics explicitly for custom loop
            optimizer = tf.keras.optimizers.Adam(learning_rate=1e-4)
            loss_obj = tf.keras.losses.SparseCategoricalCrossentropy()
            train_acc = tf.keras.metrics.SparseCategoricalAccuracy()
            train_loss = tf.keras.metrics.Mean()

        # Create a ClusterCoordinator to drive training from the chief/coordinator process
        coordinator = tf.distribute.coordinator.ClusterCoordinator(strategy)
        per_worker_ds = coordinator.create_per_worker_dataset(per_worker_dataset_fn)
        per_worker_iter = iter(per_worker_ds)

        @tf.function # Optimized tf function.
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
            for _ in range(steps_per_epoch): # Steps per epoch
                f = coordinator.schedule(per_worker_train_step, args=(per_worker_iter,))
                futures.append(f)
            # Block until all scheduled steps finish
            coordinator.join()

            print(f"Epoch {epoch+1} - loss: {train_loss.result().numpy():.4f} - accuracy: {train_acc.result().numpy():.4f}")

        # Mimic Keras History-like output for downstream logging
        history = type("_H", (), {"history": {"accuracy": [train_acc.result().numpy()]}})()
    else:
        print("Running single-process (no distributed strategy).")
        # Build dataset for single-process training (no coordinator)
        ds = tf.data.Dataset.from_tensor_slices((X, y))  # Format for the dataset (features, labels)
        # Shuffle with a modest buffer to avoid huge memory in coordinator and repeat
        ds = ds.shuffle(buffer_size=min(3000, len(X))).batch(batch_size).repeat()
        model = build_deep_model(input_dim, num_classes)
        history = model.fit(ds, epochs=epochs, steps_per_epoch=steps_per_epoch)

    # Save model
    save_path = os.path.join(output_dir, "model.keras")
    model.save(save_path)
    print(f"Model saved to: {save_path}")
    history_as_dict = history.history
    json.dump(history_as_dict, open(os.path.join(output_dir, "history.json"), "w"))

def run_image_training(
    data_dir: str,
    output_dir: str,
    epochs: int,
    batch_size: int,
    use_parameter_server: bool,
    worker_replicas: int,
    ps_replicas: int,
    img_height: int,
    img_width: int,
    port: int = 2222,
    worker_addrs: Optional[List[str]] = None,
    ps_addrs: Optional[List[str]] = None,
    chief_addr: Optional[str] = None,
    chief_port: int = 2223,
    flat_layer: bool = False,
) -> None:
    """
    Train a CNN regressor to predict (x_px, y_px) in pixels using a flat image
    directory and clean_labels.jsonl.
    """
    os.makedirs(output_dir, exist_ok=True)

    input_shape = (img_height, img_width, 3)
    steps_per_epoch = max(1, count_images(data_dir) // batch_size)

    if use_parameter_server and (worker_replicas > 0):
        print("Using ParameterServerStrategy with workers and ps for image training.")
        if worker_addrs:
            print("Worker addrs:", worker_addrs)
        if ps_addrs:
            print("PS addrs:", ps_addrs)
        strategy = make_parameter_server_strategy(
            worker_replicas, ps_replicas, port, worker_addrs, ps_addrs, chief_addr, chief_port
        )

        def per_worker_dataset_fn(input_context: Optional[tf.distribute.InputContext] = None):
            return make_image_dataset(
                data_dir=data_dir,
                image_size=(img_height, img_width),
                batch_size=batch_size,
                shuffle=True,
                input_context=input_context,
            )

        with strategy.scope():
            model = build_cnn_model(input_shape, num_outputs=2, flat=flat_layer)
            optimizer = tf.keras.optimizers.Adam(learning_rate=1e-4)
            loss_obj = tf.keras.losses.MeanSquaredError()
            train_mae = tf.keras.metrics.MeanAbsoluteError(name="mae")
            train_mse = tf.keras.metrics.MeanSquaredError(name="mse")
            train_loss = tf.keras.metrics.Mean(name="loss")

        coordinator = tf.distribute.coordinator.ClusterCoordinator(strategy)
        per_worker_ds = coordinator.create_per_worker_dataset(per_worker_dataset_fn)
        per_worker_iter = iter(per_worker_ds)

        @tf.function
        def per_worker_train_step(iterator):
            def step_fn(inputs):
                features, labels = inputs  # labels shape: (None, 2)
                with tf.GradientTape() as tape:
                    preds = model(features, training=True)
                    loss = loss_obj(labels, preds)
                    loss += tf.add_n(model.losses) if model.losses else 0.0
                grads = tape.gradient(loss, model.trainable_variables)
                optimizer.apply_gradients(zip(grads, model.trainable_variables))
                train_mae.update_state(labels, preds)
                train_mse.update_state(labels, preds)
                train_loss.update_state(loss)
                return loss

            return strategy.run(step_fn, args=(next(iterator),))

        for epoch in range(epochs):
            print(f"Starting epoch {epoch+1}/{epochs}...")
            train_mae.reset_state()
            train_mse.reset_state()
            train_loss.reset_state()

            futures = []
            for _ in range(steps_per_epoch):
                f = coordinator.schedule(per_worker_train_step, args=(per_worker_iter,))
                futures.append(f)
            coordinator.join()

            print(
                f"Epoch {epoch+1} - loss: {train_loss.result().numpy():.4f} - mae: {train_mae.result().numpy():.4f} - mse: {train_mse.result().numpy():.4f}"
            )

        # Keras History-like
        history = type("_H", (), {"history": {"mae": [train_mae.result().numpy()], "mse": [train_mse.result().numpy()], "loss": [train_loss.result().numpy()]}})()
    else:
        print("Running single-process image training.")
        ds = make_image_dataset(
            data_dir=data_dir,
            image_size=(img_height, img_width),
            batch_size=batch_size,
            shuffle=True,
            input_context=None,
        )
        model = build_cnn_model(input_shape, num_outputs=2, flat=flat_layer,)
        # log_dir = "logs/fit/" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        # tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=log_dir, histogram_freq=1)
        # history = model.fit(ds, epochs=epochs, steps_per_epoch=steps_per_epoch, callbacks=[tensorboard_callback])
        history = model.fit(ds, epochs=epochs, steps_per_epoch=steps_per_epoch)
        plt.plot(history.history['mae'])
        plt.xlabel('epoch')
        plt.show()

    save_path = os.path.join(output_dir, "model.keras")
    model.save(save_path)
    print(f"Model saved to: {save_path}")
    history_as_dict = history.history
    json.dump(history_as_dict, open(os.path.join(output_dir, "history.json"), "w"))

    final_mae = history.history.get("mae", [None])[-1]
    final_mse = history.history.get("mse", [None])[-1]
    final_loss = history.history.get("loss", [None])[-1]



def parse_args(argv: List[str]):
    parser = argparse.ArgumentParser(description="Train TF Keras model on CSV or images (folder-per-class) with optional ParameterServerStrategy")
    parser.add_argument("--data-path", default=os.environ.get("DATA_PATH", "/app/infra/local/mysql-database/datasets/image-datasets/laser-spots"), help="Path to CSV or image root directory")
    parser.add_argument("--data-url", default=os.environ.get("DATA_URL", "/app/infra/local/mysql-database/datasets/csvs/health.csv"), help="HTTP(S) URL to CSV (used inside cluster if path not mounted)")
    parser.add_argument("--data-is-images", action="store_false", help="Treat data-path as folder-per-class image dataset")
    parser.add_argument("--img-height", type=int, default=int(os.environ.get("IMG_HEIGHT", "256")), help="Image height for resizing")
    parser.add_argument("--img-width", type=int, default=int(os.environ.get("IMG_WIDTH", "320")), help="Image width for resizing")
    parser.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", "./tf-model"))
    parser.add_argument("--epochs", type=int, default=int(os.environ.get("EPOCHS", "150")))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("BATCH_SIZE", "32")))
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
    # Configure GPU to prevent out-of-memory errors
    gpus = tf.config.list_physical_devices("GPU")
    if gpus:
        try:
            # Allow multiple devices to be used
            tf.config.set_soft_device_placement(True)
            # Restrict TensorFlow to only allocate memory as needed
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
        except RuntimeError as e:
            # Memory growth must be set before GPUs have been initialized
            print(e)
    args = parse_args(sys.argv[1:])
    input("Press enter to continue...")
    # Resolve data source
    data_source = args.data_path
    # data_source = args.data_url

    worker_addrs = [s.strip() for s in args.worker_addrs.split(",") if s.strip()] if args.worker_addrs else None
    ps_addrs = [s.strip() for s in args.ps_addrs.split(",") if s.strip()] if args.ps_addrs else None

    is_image_mode = bool(args.data_is_images) or os.path.isdir(data_source)

    if is_image_mode:
        run_image_training(
            data_dir=data_source,
            output_dir=args.output_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            use_parameter_server=args.use_ps,
            worker_replicas=args.worker_replicas,
            ps_replicas=args.ps_replicas,
            img_height=args.img_height,
            img_width=args.img_width,
            port=args.port,
            worker_addrs=worker_addrs,
            ps_addrs=ps_addrs,
            chief_addr=(args.chief_addr if args.chief_addr else None),
            chief_port=args.chief_port,
            flat_layer=True,
        )
    else:
        run_deep_training(
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
