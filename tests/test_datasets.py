"""Loader logic runs against tiny temporary archives built here, which follow the schemas documented
in IMPLEMENTATION_PLAN. They exercise parsing only and never reach the app. Tests against the real
archives skip unless the files are present on this machine.
"""
import os
import zipfile

import pytest

from simulation import dataset_loader as dl


def _write_zip(folder, archive, member, text):
    with zipfile.ZipFile(os.path.join(folder, archive), "w") as z:
        z.writestr(member, text)


CLOUD = ("Task_Type,Task_Execution_Time (ms),Task_Waiting_Time (ms),Network_Bandwidth_Utilization (Mbps),"
         "Predicted_Execution_Duration (ms)\n"
         "IO-Bound,100,10,1.5,50\nIO-Bound,300,30,2.5,-173\nCPU-Bound,200,20,3.0,60\n")
VMCLOUD = ("cpu_usage,network_traffic,execution_time,task_type\n"
           "10,5.5,2.0,compute\n,6.0,3.0,io\n30,,4.0,network\n40,7.5,0.5,io\n")
FLOWS = ("Protocol,Packet Count,Avg Packet Size (Bytes),Flow Duration (ms)\n"
         "TLS,10,1000,1000\nTLS,20,500,2000\nDNS,10,480,600\n")
WIRESHARK = ('"No.","Time","Source","Destination","Protocol","Length","Info"\n'
             '1,0.1,a,b,TLSv1.3,1000,x\n2,0.9,a,b,TCP,500,x\n3,3.5,a,b,TLSv1.3,250,x\n')
LARGE = "Traffic Volume (Bytes),Packet Size,Label\n100,10,a\n200,20,b\n300,30,c\n"
IPASN = "date,l_ipn,r_asn,f\n2006-07-01,0,701,1\n"


@pytest.fixture()
def fake_resources(tmp_path, monkeypatch):
    folder = str(tmp_path)
    _write_zip(folder, "archive (2).zip", "cloud.csv", CLOUD)
    _write_zip(folder, "archive (3).zip", "vmCloud_data.csv", VMCLOUD)
    _write_zip(folder, "archive (4).zip", "nested/Network_Traffic_Dataset_1k.csv", FLOWS)
    _write_zip(folder, "archive (5).zip", "Midterm_53_group.csv", WIRESHARK)
    _write_zip(folder, "archive.zip", "Network_Traffic/Network_Traffic_Dataset/processed_dataset.csv", LARGE)
    _write_zip(folder, "archive (1).zip", "cs448b_ipasn.csv", IPASN)
    monkeypatch.setenv("ADAPTIVECRYPT_RESOURCES", folder)
    return folder


def test_cloud_filters_negative_and_converts_units(fake_resources):
    out = dl.load_cloud_workload_summary()
    assert out["rows_after_cleaning"] == 2
    assert out["data_origin"] == "EXTERNAL_DATASET_TRACE"
    io_row = next(r for r in out["by_task_type"] if r["Task_Type"] == "IO-Bound")
    assert io_row["tasks"] == 1 and io_row["mean_bandwidth_kbps"] == pytest.approx(1500.0)


def test_vmcloud_drops_missing_rows(fake_resources):
    out = dl.load_vmcloud_sample(max_rows=10)
    assert len(out["records"]) == 2
    assert all(v is not None and v == v for r in out["records"] for v in r.values())
    assert out["data_origin"] == "EXTERNAL_DATASET_TRACE"


def test_network_flows_derives_rate(fake_resources):
    out = dl.load_network_flows_1k()
    tls = next(r for r in out["by_protocol"] if r["Protocol"] == "TLS")
    assert tls["flows"] == 2 and tls["median_effective_kbps"] == pytest.approx(60.0)
    assert out["data_origin"] == "EXTERNAL_DATASET_TRACE"


def test_wireshark_buckets_keep_silent_seconds(fake_resources):
    out = dl.load_wireshark_capture_timeseries()
    assert [w["timestamp"] for w in out["windows"]] == [0.0, 1.0, 2.0, 3.0]
    assert out["windows"][0]["bandwidth_kbps"] == pytest.approx(12.0)
    assert out["windows"][0]["tls13_frames"] == 1
    assert out["windows"][1]["bandwidth_kbps"] == 0
    assert out["data_origin"] == "EXTERNAL_DATASET_TRACE"


def test_large_traffic_quantiles_use_numeric_columns(fake_resources):
    out = dl.load_large_traffic_quantiles()
    assert set(out["quantiles"]) == {"Traffic Volume (Bytes)", "Packet Size"}
    assert out["quantiles"]["Packet Size"]["0.5"] == pytest.approx(20.0)
    assert out["data_origin"] == "EXTERNAL_DATASET_TRACE"


@pytest.mark.parametrize("name", ["wireshark_midterm53", "cloud_tasks", "vmcloud_trace"])
def test_replay_traces(fake_resources, name):
    trace = dl.load_replay_trace(name)
    assert trace and all(s["bandwidth_kbps"] >= 0 for s in trace)


def test_summary_marks_ipasn_excluded(fake_resources):
    entries = {e["id"]: e for e in dl.datasets_summary()}
    assert len(entries) == 6
    assert entries["ipasn"]["excluded"] and entries["ipasn"]["summary"] == {}
    assert all(e["available"] for e in entries.values())
    assert all(e["data_origin"] == "EXTERNAL_DATASET_TRACE" for e in entries.values())


def test_missing_archive_is_reported_not_synthesized(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTIVECRYPT_RESOURCES", str(tmp_path))
    monkeypatch.setattr(dl, "search_paths", lambda: [str(tmp_path)])
    with pytest.raises(dl.DatasetUnavailableError):
        dl.load_cloud_workload_summary()
    entries = dl.datasets_summary()
    assert all(not e["available"] and e["error"] and e["summary"] == {} for e in entries)


def _real_archive(key):
    try:
        dl._archive_path(key)
    except dl.DatasetUnavailableError:
        pytest.skip(f"Real archive {dl.ARCHIVES[key][0]} is not on this machine")


def test_real_cloud_archive():
    _real_archive("cloud")
    assert dl.load_cloud_workload_summary()["rows_after_cleaning"] > 0


def test_real_vmcloud_archive():
    _real_archive("vmcloud")
    records = dl.load_vmcloud_sample(max_rows=100)["records"]
    assert len(records) == 100 and all(v is not None for r in records for v in r.values())


def test_real_network_flows_archive():
    _real_archive("network_flows")
    assert dl.load_network_flows_1k()["rows"] == 1000


def test_real_wireshark_archive():
    _real_archive("wireshark")
    assert dl.load_wireshark_capture_timeseries()["windows"]


def test_real_large_traffic_archive():
    _real_archive("large_traffic")
    assert dl.load_large_traffic_quantiles()["quantiles"]
