from datavizhub.api.workers.executor import _args_dict_to_argv


def test_convert_format_arg_mapping():
    argv = _args_dict_to_argv(
        "process",
        "convert-format",
        {"input": "in.grib2", "format": "netcdf", "output": "out.nc"},
    )
    # Stage and command leading
    assert argv[:2] == ["process", "convert-format"]
    # Positional input and format preserved, then flags
    assert "in.grib2" in argv
    assert "netcdf" in argv
    # Output should appear as flag pair
    assert "--output" in argv
    i = argv.index("--output")
    assert argv[i + 1] == "out.nc"


def test_acquire_http_arg_mapping():
    argv = _args_dict_to_argv(
        "acquire",
        "http",
        {"input": "https://example.com/a.bin", "output": "-"},
    )
    assert argv[:2] == ["acquire", "http"]
    # URL positional
    assert "https://example.com/a.bin" in argv
    # Output flag
    assert "--output" in argv


def test_aliases_dest_target_and_src():
    # dest -> output for process convert-format
    argv = _args_dict_to_argv(
        "process",
        "convert-format",
        {"src": "in.grib2", "format": "netcdf", "dest": "out.nc"},
    )
    assert argv[:2] == ["process", "convert-format"]
    assert "in.grib2" in argv and "netcdf" in argv
    assert "--output" in argv
    i = argv.index("--output")
    assert argv[i + 1] == "out.nc"

    # target -> output for acquire http
    argv = _args_dict_to_argv(
        "acquire", "http", {"input": "https://e/x", "target": "-"}
    )
    assert "--output" in argv

    # dest -> path for decimate local
    argv = _args_dict_to_argv(
        "decimate", "local", {"input": "-", "dest": "./out.bin"}
    )
    assert argv[:2] == ["decimate", "local"]
    # path should be positional at the end
    assert argv[-1] == "./out.bin"
