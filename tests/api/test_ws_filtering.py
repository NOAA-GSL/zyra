from __future__ import annotations

from zyra.api.routers.ws import _ws_should_send


def test_ws_filter_progress_only_filters_out_logs() -> None:
    allowed = {"progress"}
    assert _ws_should_send('{"progress": 0.1}', allowed) is True
    assert _ws_should_send('{"stdout": "hello"}', allowed) is False
    assert _ws_should_send('{"stderr": "err"}', allowed) is False
    # No allowed set means send everything
    assert _ws_should_send('{"stdout": "hello"}', None) is True
