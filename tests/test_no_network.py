"""Check 6: tests cannot reach the network. pytest-socket is on for the whole suite."""

import socket

import pytest
from pytest_socket import SocketBlockedError


def test_sockets_are_blocked() -> None:
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_disable_socket_is_in_pytest_config() -> None:
    import tomllib
    from pathlib import Path

    cfg = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert "--disable-socket" in cfg["tool"]["pytest"]["ini_options"]["addopts"]
