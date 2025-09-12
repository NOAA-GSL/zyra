# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock, patch

from zyra.connectors.backends import http as http_backend
from zyra.connectors.backends import s3 as s3_backend


def test_http_get_size_head():
    with patch("zyra.connectors.backends.http.requests.head") as m_head:
        r = Mock()
        r.raise_for_status = lambda: None
        r.headers = {"Content-Length": "123"}
        m_head.return_value = r
        assert http_backend.get_size("https://example.com/x.bin") == 123


def test_s3_get_size():
    with patch("zyra.connectors.backends.s3.boto3.client") as m_client:
        c = m_client.return_value
        c.head_object.return_value = {"ContentLength": 456}
        assert s3_backend.get_size("s3://bucket/key") == 456
