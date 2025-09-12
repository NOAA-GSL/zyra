# SPDX-License-Identifier: Apache-2.0
from zyra.utils.cli_helpers import sanitize_args, sanitize_for_log


def test_sanitize_for_log_redacts_basic_auth_password():
    s = "https://user:secretpass@example.com/path"
    out = sanitize_for_log(s)
    assert "secretpass" not in out
    assert ":***@" in out


def test_sanitize_for_log_redacts_common_query_tokens():
    s = (
        "https://example.com/api?token=abc123&signature=zzz&X-Amz-Signature=Sig&"
        "apikey=K&access_key=AKIA&client_secret=CS&refresh_token=RT&authorization_code=AC"
    )
    out = sanitize_for_log(s)
    assert "abc123" not in out
    assert "zzz" not in out
    # Ensure the value is masked (allowing the name to contain 'Signature')
    assert "=Sig" not in out
    assert "K" not in out
    assert "AKIA" not in out
    assert "CS" not in out
    assert "RT" not in out
    assert "AC" not in out
    # Keep parameter names, values masked
    assert "token=***" in out
    assert "signature=***" in out
    assert "x-amz-signature=***" in out.lower()
    assert "apikey=***" in out
    assert "access_key=***" in out
    assert "client_secret=***" in out
    assert "refresh_token=***" in out
    assert "authorization_code=***" in out


def test_sanitize_for_log_redacts_bearer_auth_header():
    s = "Authorization: Bearer verysecrettoken123"
    out = sanitize_for_log(s)
    assert out.lower().startswith("authorization: bearer ")
    assert out.strip().endswith("***")


def test_sanitize_args_vectorizes():
    args = [
        "ffmpeg",
        "-i",
        "https://user:pw@example.com/v.m3u8?token=T",
        "--header",
        "Authorization: Bearer XYZ",
    ]
    out = sanitize_args(args)
    assert out[2] != args[2]
    assert ":***@" in out[2]
    assert "token=***" in out[2]
    assert out[4].endswith("***")
