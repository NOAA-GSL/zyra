from unittest.mock import patch, Mock

from datavizhub.acquisition.s3_manager import S3Manager


def test_s3_unsigned_client_and_ranges():
    with patch("datavizhub.acquisition.s3_manager.boto3.client") as m_client:
        client = Mock()
        m_client.return_value = client
        client.head_object.return_value = {"ContentLength": 20}

        client.get_object.side_effect = [
            {"Body": Mock(read=lambda: b"1:0:a:b:c:d:e\n2:10:a:b:c:d:e\n")},
            {"Body": Mock(read=lambda: b"0123456789")},
            {"Body": Mock(read=lambda: b"abcdefghij")},
        ]

        mgr = S3Manager(None, None, "bucket", unsigned=True)
        mgr.connect()
        assert mgr.get_size("key") == 20

        lines = mgr.get_idx_lines("key")
        assert lines and len(lines) == 2
        br = mgr.idx_to_byteranges(lines, r"b")
        data = mgr.download_byteranges("key", br.keys(), max_workers=2)
        assert data == b"0123456789abcdefghij"
