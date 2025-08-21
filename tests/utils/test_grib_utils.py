from zyra.utils.grib import (
    compute_chunks,
    ensure_idx_path,
    idx_to_byteranges,
    parse_idx_lines,
)


def test_ensure_idx_path():
    assert ensure_idx_path("file.grib2") == "file.grib2.idx"
    assert ensure_idx_path("file.idx") == "file.idx"


def test_parse_and_ranges():
    # Minimal idx content: line format is "<num>:<start>:<date>:<var>:<level>:<fcst>:..."
    idx_text = (
        "1:0:20240101:TMP:surface:anl:\n"
        "2:100:20240101:UGRD:10 m above ground:f003:\n"
        "3:250:20240101:VGRD:10 m above ground:f003:\n"
    )
    lines = parse_idx_lines(idx_text)
    assert len(lines) == 3
    # Regex that selects the 10m winds
    br = idx_to_byteranges(lines, r":(UGRD|VGRD):10 m above ground:")
    # Should produce two ranges: 100- (to before 250) and 250- (to EOF)
    keys = list(br.keys())
    assert keys[0].startswith("bytes=100-")
    assert keys[1].startswith("bytes=250-")


def test_compute_chunks():
    ranges = compute_chunks(1024, chunk_size=256)
    # 1024 bytes / 256 -> 4 ranges
    assert len(ranges) == 4
    assert ranges[0] == "bytes=0-255"
    assert ranges[-1] == "bytes=768-1024"
