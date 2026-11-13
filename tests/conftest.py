"""Default-deny network policy for the repository test suite."""

import socket

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Enable explicitly marked live integration tests",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-live"):
        marker = pytest.mark.skip(reason="Live tests require --run-live")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(marker)


@pytest.fixture(autouse=True)
def deny_network_by_default(request, monkeypatch):
    if request.node.get_closest_marker("live") and request.config.getoption("--run-live"):
        return

    def blocked(*args, **kwargs):
        raise RuntimeError("Network access is disabled in offline tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
