"""
Shared pytest fixtures for the auto_docker_proxy test suite.

Provides mock Docker client, configuration, and logger fixtures
to isolate tests from real Docker daemon and filesystem dependencies.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from config import (
    Config,
    DockerConfig,
    DockerTLSConfig,
    LogLevelConfig,
    TLSCertificateConfig,
    TraefikConfig,
)


def make_test_config(**overrides):
    """
    Build a Config NamedTuple with sensible test defaults.

    Parameters
    ----------
    overrides : dict
        Keyword arguments whose keys match Config field paths.
        Currently unused but kept for future extensibility.

    Returns
    -------
    Config
        A fully populated Config instance suitable for unit tests.
    """
    tls = DockerTLSConfig(
        enabled=False,
        verify=TLSCertificateConfig(file="/path/to/ca.pem"),
        cert=TLSCertificateConfig(file="/path/to/cert.pem"),
        key=TLSCertificateConfig(file="/path/to/key.pem"),
    )
    docker = DockerConfig(host="unix:///var/run/docker.sock", tls=tls)
    log_level = LogLevelConfig(general="INFO", application="DEBUG")
    traefik = TraefikConfig(
        containerName="traefik",
        monitoredLabel="^traefik.enable$",
        networkLabel="traefik.docker.network",
    )
    return Config(docker=docker, logLevel=log_level, traefik=traefik)


@pytest.fixture
def mock_docker_client():
    """
    Patch ``main.client`` with a MagicMock so no real Docker daemon is needed.

    Yields
    ------
    MagicMock
        The mock object replacing ``main.client``.
    """
    with patch("main.client") as mock_client:
        yield mock_client


@pytest.fixture
def mock_config():
    """
    Patch ``main.config`` with a realistic test Config NamedTuple.

    Yields
    ------
    Config
        The test configuration injected into ``main.config``.
    """
    cfg = make_test_config()
    with patch("main.config", cfg):
        yield cfg


@pytest.fixture
def mock_logger():
    """
    Patch ``main.app_logger`` with a MagicMock to capture log calls.

    Yields
    ------
    MagicMock
        The mock object replacing ``main.app_logger``.
    """
    with patch("main.app_logger") as mock_log:
        yield mock_log
