import json

from datavizhub.transform import register_cli as register_transform


def _run_update(tmp_path, src_obj):
    ds = tmp_path / "ds.json"
    ds.write_text(json.dumps(src_obj))
    meta = {
        "start_datetime": "2024-01-01T00:00:00",
        "end_datetime": "2024-01-22T00:00:00",
        "vimeo_uri": "/videos/900",
    }
    mf = tmp_path / "m.json"
    mf.write_text(json.dumps(meta))
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
    return json.loads((tmp_path / "out.json").read_text())


def test_update_top_level_array(tmp_path):
    src = [
        {"id": "OTHER"},
        {
            "id": "INTERNAL_SOS_DROUGHT_RT",
            "startTime": None,
            "endTime": None,
            "dataLink": "",
        },
    ]
    out = _run_update(tmp_path, src)
    match = [e for e in out if e.get("id") == "INTERNAL_SOS_DROUGHT_RT"][0]
    assert match["startTime"].startswith("2024-01-01")
    assert match["endTime"].startswith("2024-01-22")
    assert match["dataLink"].endswith("/900")


def test_update_object_with_datasets_list(tmp_path):
    src = {
        "datasets": [
            {
                "id": "INTERNAL_SOS_DROUGHT_RT",
                "startTime": None,
                "endTime": None,
                "dataLink": "",
            }
        ]
    }
    out = _run_update(tmp_path, src)
    match = [e for e in out["datasets"] if e.get("id") == "INTERNAL_SOS_DROUGHT_RT"][0]
    assert match["startTime"].startswith("2024-01-01")
    assert match["endTime"].startswith("2024-01-22")
    assert match["dataLink"].endswith("/900")


def test_update_single_object(tmp_path):
    src = {
        "id": "INTERNAL_SOS_DROUGHT_RT",
        "startTime": None,
        "endTime": None,
        "dataLink": "",
    }
    out = _run_update(tmp_path, src)
    assert out["startTime"].startswith("2024-01-01")
    assert out["endTime"].startswith("2024-01-22")
    assert out["dataLink"].endswith("/900")
