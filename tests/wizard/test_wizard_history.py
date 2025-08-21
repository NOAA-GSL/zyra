import importlib
import json


def test_history_append_and_load(tmp_path, monkeypatch):
    # Isolate HOME so wizard stores under tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))
    wiz = importlib.import_module("zyra.wizard")

    # Ensure clean state
    wiz._clear_history_file()
    hist_path = wiz._history_file_path()
    assert not hist_path.exists()

    # Append a couple of commands
    cmd1 = "datavizhub process subset --input a.nc --var t"
    cmd2 = "datavizhub visualize heatmap --input b.nc --var temp"
    wiz._append_history(cmd1)
    wiz._append_history(cmd2)

    # File should now exist and contain two JSON lines
    assert hist_path.exists()
    lines = hist_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for ln in lines:
        obj = json.loads(ln)
        assert obj["cmd"].startswith("datavizhub ")

    # Load should return both commands
    loaded = wiz._load_persisted_history()
    assert loaded == [cmd1, cmd2]


def test_history_dedup_and_corruption(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    wiz = importlib.import_module("zyra.wizard")

    # Prepare a file with duplicates and a corrupted line
    p = wiz._history_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {"ts": "2025-01-01T00:00:00Z", "cmd": "datavizhub x a"},
        {"ts": "2025-01-01T00:00:01Z", "cmd": "datavizhub x a"},  # consecutive dup
        {"ts": "2025-01-01T00:00:02Z", "cmd": "datavizhub y b"},
    ]
    with p.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
        f.write("{not-json}\n")  # corrupted

    loaded = wiz._load_persisted_history()
    # Deduped consecutive duplicate => first 'x a' kept once
    assert loaded == ["datavizhub x a", "datavizhub y b"]


def test_clear_history(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    wiz = importlib.import_module("zyra.wizard")

    wiz._append_history("datavizhub foo")
    assert wiz._history_file_path().exists()
    wiz._clear_history_file()
    assert not wiz._history_file_path().exists()
