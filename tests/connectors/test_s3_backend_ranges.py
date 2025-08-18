from unittest.mock import Mock, patch

from datavizhub.connectors.backends import s3 as s3_backend


def test_s3_unsigned_client_and_ranges():
    with patch("datavizhub.connectors.backends.s3.boto3.client") as m_client:
        client = Mock()
        m_client.return_value = client
        client.head_object.return_value = {"ContentLength": 20}

        client.get_object.side_effect = [
            {"Body": Mock(read=lambda: b"1:0:a:b:c:d:e\n2:10:a:b:c:d:e\n")},
            {"Body": Mock(read=lambda: b"0123456789")},
            {"Body": Mock(read=lambda: b"abcdefghij")},
        ]

        assert s3_backend.get_size("s3://bucket/key") == 20

        lines = s3_backend.get_idx_lines("s3://bucket/key", unsigned=True)
        assert lines and len(lines) == 2
        from datavizhub.utils.grib import idx_to_byteranges

        br = idx_to_byteranges(lines, r"b")
        data = s3_backend.download_byteranges(
            "s3://bucket/key", None, br.keys(), unsigned=True, max_workers=2
        )
        assert data == b"0123456789abcdefghij"
