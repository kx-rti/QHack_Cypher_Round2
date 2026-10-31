"""Streaming loaders for the external dataset archives. Outputs are never cryptographic benchmarks.

Archives are looked up in ADAPTIVECRYPT_RESOURCES, then ./Resources, the project root, and
~/Downloads/Resources. A missing archive raises DatasetUnavailableError; nothing is synthesized.
"""
import os
import zipfile
from functools import lru_cache

import pandas as pd

DATA_ORIGIN = "EXTERNAL_DATASET_TRACE"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHUNK_ROWS = 50_000
_MAX_SCAN_ROWS = 200_000  # upper bound on rows read from the multi-hundred-MB archives

ARCHIVES = {
    "cloud": ("archive (2).zip", "cloud.csv"),
    "vmcloud": ("archive (3).zip", "vmCloud_data.csv"),
    "network_flows": ("archive (4).zip", "Network_Traffic_Dataset_1k.csv"),
    "wireshark": ("archive (5).zip", "Midterm_53_group.csv"),
    "large_traffic": ("archive.zip", "processed_dataset.csv"),
    "ipasn": ("archive (1).zip", "cs448b_ipasn.csv"),
}


class DatasetUnavailableError(Exception):
    """The archive or the expected member is not on this machine."""


def search_paths() -> list[str]:
    env = os.environ.get("ADAPTIVECRYPT_RESOURCES")
    return ([env] if env else []) + [
        os.path.join(_ROOT, "Resources"), _ROOT, os.path.join(os.path.expanduser("~"), "Downloads", "Resources"),
    ]


def _archive_path(key: str) -> str:
    name = ARCHIVES[key][0]
    for folder in search_paths():
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    raise DatasetUnavailableError(f"{name} was not found. Set ADAPTIVECRYPT_RESOURCES to its folder.")


def _open_member(key: str):
    """Opens the CSV inside its archive, matching by file name so nested folders still resolve."""
    path = _archive_path(key)
    target = ARCHIVES[key][1]
    archive = zipfile.ZipFile(path)
    for member in archive.namelist():
        if os.path.basename(member) == target:
            return archive, archive.open(member)
    archive.close()
    raise DatasetUnavailableError(f"{target} is not inside {os.path.basename(path)}.")


def _stream(key: str, usecols=None, max_rows: int | None = None):
    archive, handle = _open_member(key)
    with archive, handle:
        seen = 0
        for chunk in pd.read_csv(handle, chunksize=_CHUNK_ROWS, usecols=usecols):
            yield chunk
            seen += len(chunk)
            if max_rows is not None and seen >= max_rows:
                return


def _read_all(key: str, usecols=None) -> pd.DataFrame:
    return pd.concat(_stream(key, usecols=usecols), ignore_index=True)


def _records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe rows: numpy scalars become Python numbers, NaN becomes None."""
    clean = df.astype(object).where(df.notna(), None)
    return [{k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}
            for row in clean.to_dict(orient="records")]


def _numeric_summary(df: pd.DataFrame) -> dict:
    out = {}
    for column in df.select_dtypes("number").columns:
        s = df[column]
        out[column] = {"min": float(s.min()), "median": float(s.median()), "max": float(s.max())}
    return out


def _cloud_frame() -> pd.DataFrame:
    df = _read_all("cloud")
    df = df[df["Predicted_Execution_Duration (ms)"] >= 0].copy()
    df["bandwidth_kbps"] = df["Network_Bandwidth_Utilization (Mbps)"] * 1000.0
    return df


def load_cloud_workload_summary() -> dict:
    df = _cloud_frame()
    grouped = df.groupby("Task_Type").agg(
        tasks=("Task_Type", "size"),
        mean_execution_ms=("Task_Execution_Time (ms)", "mean"),
        median_waiting_ms=("Task_Waiting_Time (ms)", "median"),
        mean_bandwidth_kbps=("bandwidth_kbps", "mean"),
    ).reset_index()
    return {"rows_after_cleaning": len(df), "by_task_type": _records(grouped), "data_origin": DATA_ORIGIN}


def load_vmcloud_sample(max_rows: int = 500) -> dict:
    """First max_rows complete rows of the stream; a head sample, not a random one."""
    kept, scanned = [], 0
    for chunk in _stream("vmcloud", max_rows=_MAX_SCAN_ROWS):
        scanned += len(chunk)
        kept.append(chunk.dropna())
        if sum(len(k) for k in kept) >= max_rows:
            break
    df = pd.concat(kept, ignore_index=True).head(max_rows)
    return {"rows_scanned": scanned, "records": _records(df), "data_origin": DATA_ORIGIN}


def load_network_flows_1k() -> dict:
    df = _read_all("network_flows")
    df["flow_bytes"] = df["Packet Count"] * df["Avg Packet Size (Bytes)"]
    df["effective_kbps"] = df["flow_bytes"] * 8 / df["Flow Duration (ms)"]
    grouped = df.groupby("Protocol").agg(
        flows=("Protocol", "size"),
        mean_flow_bytes=("flow_bytes", "mean"),
        median_effective_kbps=("effective_kbps", "median"),
    ).reset_index()
    return {"rows": len(df), "by_protocol": _records(grouped), "data_origin": DATA_ORIGIN}


@lru_cache(maxsize=8)
def _wireshark_buckets(path: str, mtime: float, window_sec: float) -> tuple[tuple, ...]:
    totals: dict[int, list] = {}
    for chunk in _stream("wireshark", usecols=["Time", "Protocol", "Length"]):
        chunk = chunk.dropna(subset=["Time", "Length"])
        buckets = (chunk["Time"] // window_sec).astype(int)
        tls = chunk["Protocol"].astype(str).eq("TLSv1.3")
        grouped = pd.DataFrame({"bucket": buckets, "bytes": chunk["Length"], "tls": tls}).groupby("bucket").agg(
            bytes=("bytes", "sum"), tls=("tls", "sum"), packets=("bytes", "size"))
        for bucket, row in grouped.iterrows():
            entry = totals.setdefault(int(bucket), [0, 0, 0])
            entry[0] += float(row["bytes"])
            entry[1] += int(row["tls"])
            entry[2] += int(row["packets"])
    if not totals:
        return ()
    # Silent seconds are real measurements of zero traffic, so they stay in the trace.
    return tuple((b, *totals.get(b, (0, 0, 0))) for b in range(min(totals), max(totals) + 1))


def load_wireshark_capture_timeseries(window_sec: float = 1.0, max_windows: int = 120) -> dict:
    path = _archive_path("wireshark")
    buckets = _wireshark_buckets(path, os.path.getmtime(path), window_sec)
    windows = [{
        "timestamp": bucket * window_sec,
        "bandwidth_kbps": total_bytes * 8 / 1000 / window_sec,
        "tls13_frames": tls,
        "packets": packets,
    } for bucket, total_bytes, tls, packets in buckets]
    return {"total_windows": len(windows), "windows": windows[:max_windows], "data_origin": DATA_ORIGIN}


def load_large_traffic_quantiles(sample_size: int = 5000) -> dict:
    """Quantiles from a seeded sample of the first rows of processed_dataset.csv (physical units).

    preprocessed_dataset.csv is Min-Max scaled to unitless [0, 1], so it is not used.
    """
    frames, scanned = [], 0
    for chunk in _stream("large_traffic", max_rows=_MAX_SCAN_ROWS):
        scanned += len(chunk)
        frames.append(chunk.select_dtypes("number").dropna())
    df = pd.concat(frames, ignore_index=True)
    df = df.sample(n=min(sample_size, len(df)), random_state=7)
    quantiles = {c: {str(q): float(df[c].quantile(q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)} for c in df.columns}
    return {"rows_scanned": scanned, "sample_size": len(df), "quantiles": quantiles, "data_origin": DATA_ORIGIN}


def load_replay_trace(dataset_name: str, max_steps: int = 300) -> list[dict]:
    """Samples of (timestamp, bandwidth_kbps, latency_budget_ms or None) for hysteresis replay."""
    if dataset_name == "wireshark_midterm53":
        data = load_wireshark_capture_timeseries(max_windows=max_steps)
        return [{"timestamp": w["timestamp"], "bandwidth_kbps": w["bandwidth_kbps"], "latency_budget_ms": None}
                for w in data["windows"]]
    if dataset_name == "cloud_tasks":
        df = _cloud_frame().head(max_steps)
        return [{"timestamp": float(i), "bandwidth_kbps": float(b), "latency_budget_ms": float(w)}
                for i, (b, w) in enumerate(zip(df["bandwidth_kbps"], df["Task_Waiting_Time (ms)"]))]
    if dataset_name == "vmcloud_trace":
        records = load_vmcloud_sample(max_rows=max_steps)["records"]
        # network_traffic carries no stated unit in the dataset; it is read as kbps here.
        return [{"timestamp": float(i), "bandwidth_kbps": float(r["network_traffic"]),
                 "latency_budget_ms": max(float(r["execution_time"]), 1.0)} for i, r in enumerate(records)]
    raise ValueError(f"Unknown replay dataset: {dataset_name}")


_NOTES = {
    "cloud": "Synthetic scheduler log. Negative predicted durations are filtered out; Mbps converted to kbps.",
    "vmcloud": "Synthetic VM telemetry. Rows with missing values are dropped; this is a head-of-stream sample. "
               "network_traffic has no stated unit and is read as kbps during replay.",
    "network_flows": "Curated flows. flow_bytes = packets x size; effective_kbps = bytes x 8 / duration in ms.",
    "wireshark": "Real packet capture, aggregated into 1-second throughput windows for replay.",
    "large_traffic": "processed_dataset.csv is used for its physical units; preprocessed_dataset.csv is unitless [0, 1].",
    "ipasn": "Excluded: 2006 IP-to-ASN flow counts with no byte, latency or bandwidth fields.",
}
_LOADERS = {
    "cloud": load_cloud_workload_summary,
    "vmcloud": lambda: load_vmcloud_sample(max_rows=5),
    "network_flows": load_network_flows_1k,
    "wireshark": load_wireshark_capture_timeseries,
    "large_traffic": load_large_traffic_quantiles,
}


def datasets_summary() -> list[dict]:
    """Status of every archive. Missing or unreadable data is reported as such, never filled in."""
    out = []
    for key, (archive, member) in ARCHIVES.items():
        entry = {"id": key, "archive": archive, "member": member, "note": _NOTES[key], "data_origin": DATA_ORIGIN,
                 "available": False, "excluded": key == "ipasn", "error": "", "summary": {}}
        try:
            _archive_path(key)
            entry["available"] = True
            if key in _LOADERS:
                entry["summary"] = _LOADERS[key]()
        except DatasetUnavailableError as exc:
            entry["error"] = str(exc)
        except (KeyError, ValueError, zipfile.BadZipFile) as exc:
            entry["available"] = False
            entry["error"] = f"Could not parse the expected schema: {exc}"
        out.append(entry)
    return out
