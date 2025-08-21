import json

from zyra.transform import _compute_frames_metadata as compute_meta
from zyra.transform import register_cli as register_transform


def test_compute_frames_metadata_weekly(tmp_path):
    d = tmp_path / "frames"
    d.mkdir()
    # Create weekly-named files, leave a gap to test missing
    (d / "DroughtRisk_Weekly_20240101.png").write_bytes(b"a")
    (d / "DroughtRisk_Weekly_20240108.png").write_bytes(b"b")
    # missing 20240115
    (d / "DroughtRisk_Weekly_20240122.png").write_bytes(b"c")

    meta = compute_meta(
        str(d),
        pattern=r"DroughtRisk_Weekly_(\d{8})\.png",
        datetime_format="%Y%m%d",
        period_seconds=7 * 24 * 3600,
    )
    assert meta["frame_count_actual"] == 3
    assert meta["frame_count_expected"] >= 3
    assert any("2024-01-15" in s for s in meta.get("missing_timestamps", []))


def test_update_dataset_json_from_meta(tmp_path, monkeypatch):
    # Prepare dataset.json
    data = {
        "datasets": [
            {"id": "OTHER", "startTime": None, "endTime": None},
            {
                "id": "INTERNAL_SOS_DROUGHT_RT",
                "startTime": None,
                "endTime": None,
                "dataLink": "https://vimeo.com/old",
            },
        ]
    }
    ds = tmp_path / "dataset.json"
    ds.write_text(json.dumps(data))
    meta = {
        "start_datetime": "2024-01-01T00:00:00",
        "end_datetime": "2024-01-22T00:00:00",
        "vimeo_uri": "/videos/900",
    }
    mf = tmp_path / "meta.json"
    mf.write_text(json.dumps(meta))

    # Build a small CLI to call transform update-dataset-json
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    register_transform(sub)

    ns = parser.parse_args(
        [
            "update-dataset-json",
            "--input-file",
            str(ds),
            "--dataset-id",
            "INTERNAL_SOS_DROUGHT_RT",
            "--meta",
            str(mf),
            "-o",
            str(tmp_path / "out.json"),
        ]
    )
    rc = ns.func(ns)
    assert rc == 0
    out = json.loads((tmp_path / "out.json").read_text())
    entry = [e for e in out["datasets"] if e["id"] == "INTERNAL_SOS_DROUGHT_RT"][0]
    assert entry["startTime"] == meta["start_datetime"]
    assert entry["endTime"] == meta["end_datetime"]
    assert entry["dataLink"].endswith("/900")
