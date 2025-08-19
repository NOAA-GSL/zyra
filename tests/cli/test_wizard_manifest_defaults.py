def test_tokenizer_captures_default_and_help():
    import datavizhub.wizard as wiz

    cap = {
        "process convert-format": {
            "description": "",
            "options": {
                "--format": {
                    "help": "Output format",
                    "choices": ["netcdf", "geotiff"],
                    "default": "netcdf",
                },
                "--output": {"help": "Output file", "path_arg": True},
            },
        }
    }
    toks = wiz._tokenize_manifest(cap)
    meta = toks["opt_meta"].get(("process", "convert-format"), {})
    assert meta.get("--format", {}).get("default") == "netcdf"
    assert "help" in meta.get("--format", {})
