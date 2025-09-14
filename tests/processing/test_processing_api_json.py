# SPDX-License-Identifier: Apache-2.0
import json
from argparse import ArgumentParser

from zyra.processing import register_cli


def _build_parser():
    p = ArgumentParser()
    subs = p.add_subparsers(dest="stage")
    register_cli(subs)
    return p


def test_api_json_basic_message_to_csv(tmp_path):
    # Prepare input JSON with chat messages
    obj = {
        "data": {
            "chat": {
                "messages": [
                    {"id": "m1", "text": "Hello world!", "user": {"role": "user"}},
                    {"id": "m2", "text": "How are you?", "user": {"role": "assistant"}},
                ]
            }
        }
    }
    inp = tmp_path / "chat.json"
    inp.write_text(json.dumps(obj), encoding="utf-8")
    out = tmp_path / "out.csv"

    parser = _build_parser()
    args = parser.parse_args(
        [
            "api-json",
            str(inp),
            "--records-path",
            "data.chat.messages",
            "--fields",
            "id,text,user.role",
            "--derived",
            "word_count",
            "--output",
            str(out),
        ]
    )
    # Invoke handler
    rc = args.func(args)
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0].startswith("id,")
    assert "word_count" in lines[0]
    assert any("m1" in ln for ln in lines[1:])


def test_api_json_preset_limitless_lifelogs_defaults_records_path(tmp_path):
    # Two NDJSON pages, each carries data.lifelogs list
    page1 = json.dumps({"data": {"lifelogs": [{"id": 1, "text": "a"}]}})
    page2 = json.dumps({"data": {"lifelogs": [{"id": 2, "text": "b"}]}})
    inp = tmp_path / "lifelogs.jsonl"
    inp.write_text(page1 + "\n" + page2 + "\n", encoding="utf-8")
    out = tmp_path / "out.csv"

    parser = _build_parser()
    args = parser.parse_args(
        [
            "api-json",
            str(inp),
            "--preset",
            "limitless-lifelogs",
            "--fields",
            "id,text",
            "--output",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    txt = out.read_text(encoding="utf-8")
    assert "id,text" in txt.splitlines()[0]
    assert ",a" in txt or ",b" in txt


def test_api_json_strict_errors_on_missing_field(tmp_path):
    obj = {"data": {"items": [{"id": 1}, {"id": 2}]}}
    inp = tmp_path / "items.json"
    inp.write_text(json.dumps(obj), encoding="utf-8")
    out = tmp_path / "out.csv"

    parser = _build_parser()
    args = parser.parse_args(
        [
            "api-json",
            str(inp),
            "--records-path",
            "data.items",
            "--fields",
            "id,text",
            "--strict",
            "--output",
            str(out),
        ]
    )
    try:
        _ = args.func(args)
    except SystemExit as e:  # noqa: PT012
        assert "Missing required field" in str(e)
    else:  # pragma: no cover
        assert False, "Expected strict mode to error on missing field"


def test_api_json_non_strict_emits_empty_for_missing_field_jsonl(tmp_path):
    obj = {"data": {"items": [{"id": 1}, {"id": 2}]}}
    inp = tmp_path / "items2.json"
    inp.write_text(json.dumps(obj), encoding="utf-8")
    out = tmp_path / "out.jsonl"

    parser = _build_parser()
    args = parser.parse_args(
        [
            "api-json",
            str(inp),
            "--records-path",
            "data.items",
            "--fields",
            "id,text",
            "--format",
            "jsonl",
            "--output",
            str(out),
        ]
    )
    rc = args.func(args)
    assert rc == 0
    lines = [
        json.loads(ln)
        for ln in out.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert lines and all("id" in r and "text" in r for r in lines)
    # text should be empty string when missing
    assert all((r.get("text") == "") for r in lines)
