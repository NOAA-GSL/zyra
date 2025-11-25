# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from zyra.narrate.swarm import (
    _summarize_frames_context,
    _summarize_verify_context,
)


def test_summarize_frames_context_builds_sentence(tmp_path):
    data = {
        "frames_metadata": {
            "frame_count_actual": 5,
            "start_datetime": "2024-01-01T00:00:00",
            "end_datetime": "2024-01-01T01:00:00",
            "missing_timestamps": ["2024-01-01T00:30:00"],
        },
        "frames_analysis": {
            "span_seconds": 3600,
            "sample_frames": [
                {"label": "start", "path": str(tmp_path / "start.png")},
                {"path": str(tmp_path / "mid.png")},
            ],
            "missing_timestamps": ["2024-01-01T00:30:00"],
        },
    }
    summary = _summarize_frames_context(data)
    assert "5 frames" in summary
    assert "span" in summary
    assert "start" in summary
    assert "00:30" in summary


def test_summarize_verify_context_includes_verdict():
    data = {
        "verify_results": [
            {
                "metric": "completeness",
                "verdict": "passed",
                "message": "verify evaluate: completeness PASSED - all frames present",
            }
        ]
    }
    summary = _summarize_verify_context(data)
    assert "completeness passed" in summary.lower()
    assert "all frames present" in summary.lower()
