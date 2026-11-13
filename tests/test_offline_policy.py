import socket

import pytest


def test_default_suite_blocks_socket_connect():
    with socket.socket() as sock:
        with pytest.raises(RuntimeError, match="Network access is disabled"):
            sock.connect_ex(("127.0.0.1", 0))
