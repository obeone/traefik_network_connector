"""
Unit tests for config.py.

Tests cover pure utility functions (flatten_keys, merge_dicts),
configuration loading, environment variable overrides, CLI argument
overrides, and logger initialization.
"""

import logging
import os
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest
import yaml

from config import (
    Config,
    DockerConfig,
    DockerTLSConfig,
    LogLevelConfig,
    TLSCertificateConfig,
    TraefikConfig,
    flatten_keys,
    init_loggers,
    load_config,
    merge_dicts,
)


# ---------------------------------------------------------------------------
# flatten_keys
# ---------------------------------------------------------------------------


class TestFlattenKeys:
    """Tests for the flatten_keys utility function."""

    def test_flat_dict(self):
        """Flat dict should be returned unchanged."""
        assert flatten_keys({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    def test_nested_dict(self):
        """Nested dict should produce dot-separated keys."""
        result = flatten_keys({"a": {"b": 1, "c": 2}})
        assert result == {"a.b": 1, "a.c": 2}

    def test_deeply_nested(self):
        """Multiple levels of nesting should be flattened correctly."""
        result = flatten_keys({"a": {"b": {"c": 3}}})
        assert result == {"a.b.c": 3}

    def test_with_parent_key(self):
        """Parent key should be prepended to all keys."""
        result = flatten_keys({"b": 1}, parent_key="a")
        assert result == {"a.b": 1}

    def test_empty_dict(self):
        """Empty dict should return an empty dict."""
        assert flatten_keys({}) == {}

    def test_custom_separator(self):
        """Custom separator should be used between key levels."""
        result = flatten_keys({"a": {"b": 1}}, sep="_")
        assert result == {"a_b": 1}


# ---------------------------------------------------------------------------
# merge_dicts
# ---------------------------------------------------------------------------


class TestMergeDicts:
    """Tests for the merge_dicts utility function."""

    def test_rhs_wins_on_conflict(self):
        """Right-hand side values should overwrite left-hand side on conflict."""
        result = merge_dicts({"a": 1}, {"a": 2})
        assert result == {"a": 2}

    def test_disjoint_keys(self):
        """Disjoint keys should all appear in the result."""
        result = merge_dicts({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_nested_merge(self):
        """Nested dicts should be merged recursively."""
        lhs = {"a": {"x": 1, "y": 2}}
        rhs = {"a": {"y": 3, "z": 4}}
        result = merge_dicts(lhs, rhs)
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_lhs_not_mutated(self):
        """Original lhs dict should not be mutated."""
        lhs = {"a": 1}
        merge_dicts(lhs, {"a": 2})
        assert lhs == {"a": 1}

    def test_rhs_overwrites_dict_with_scalar(self):
        """A scalar in rhs should overwrite a dict in lhs."""
        result = merge_dicts({"a": {"b": 1}}, {"a": 42})
        assert result == {"a": 42}


# ---------------------------------------------------------------------------
# load_config — default values
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for the load_config function with default config.yaml."""

    def test_load_config_returns_config_type(self):
        """load_config should return a Config NamedTuple."""
        with patch("sys.argv", ["prog"]):
            cfg = load_config()
        assert isinstance(cfg, Config)

    def test_default_docker_host(self):
        """Default Docker host should match config.yaml."""
        with patch("sys.argv", ["prog"]):
            cfg = load_config()
        assert cfg.docker.host == "unix:///var/run/docker.sock"

    def test_default_tls_disabled(self):
        """TLS should be disabled by default."""
        with patch("sys.argv", ["prog"]):
            cfg = load_config()
        assert cfg.docker.tls.enabled is False

    def test_default_traefik_container_name(self):
        """Default Traefik container name should be 'traefik'."""
        with patch("sys.argv", ["prog"]):
            cfg = load_config()
        assert cfg.traefik.containerName == "traefik"

    def test_default_monitored_label(self):
        """Default monitored label should be the traefik.enable regex."""
        with patch("sys.argv", ["prog"]):
            cfg = load_config()
        assert cfg.traefik.monitoredLabel == "^traefik.enable$"

    def test_default_network_label(self):
        """Default network label should be 'traefik.docker.network'."""
        with patch("sys.argv", ["prog"]):
            cfg = load_config()
        assert cfg.traefik.networkLabel == "traefik.docker.network"


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


class TestEnvOverrides:
    """Tests for environment variable overrides in load_config."""

    def test_docker_host_override(self):
        """DOCKER_HOST env var should override the default Docker host."""
        with patch("sys.argv", ["prog"]), \
             patch.dict(os.environ, {"DOCKER_HOST": "tcp://1.2.3.4:2375"}):
            cfg = load_config()
        assert cfg.docker.host == "tcp://1.2.3.4:2375"

    def test_traefik_containername_override(self):
        """TRAEFIK_CONTAINERNAME env var should override container name."""
        with patch("sys.argv", ["prog"]), \
             patch.dict(os.environ, {"TRAEFIK_CONTAINERNAME": "my-traefik"}):
            cfg = load_config()
        assert cfg.traefik.containerName == "my-traefik"

    def test_traefik_monitoredlabel_override(self):
        """TRAEFIK_MONITOREDLABEL env var should override the monitored label."""
        with patch("sys.argv", ["prog"]), \
             patch.dict(os.environ, {"TRAEFIK_MONITOREDLABEL": "^custom.label$"}):
            cfg = load_config()
        assert cfg.traefik.monitoredLabel == "^custom.label$"

    def test_loglevel_application_override(self):
        """LOGLEVEL_APPLICATION env var should override application log level."""
        with patch("sys.argv", ["prog"]), \
             patch.dict(os.environ, {"LOGLEVEL_APPLICATION": "ERROR"}):
            cfg = load_config()
        assert cfg.logLevel.application == "ERROR"

    def test_docker_tls_enabled_override(self):
        """DOCKER_TLS_ENABLED env var should override TLS enabled flag."""
        with patch("sys.argv", ["prog"]), \
             patch.dict(os.environ, {"DOCKER_TLS_ENABLED": "True"}):
            cfg = load_config()
        # The default value is a bool (False), so type(value)("True") → bool("True") → True
        assert cfg.docker.tls.enabled is True

    def test_docker_tls_verify_override(self):
        """DOCKER_TLS_VERIFY env var should override TLS verify path."""
        with patch("sys.argv", ["prog"]), \
             patch.dict(os.environ, {"DOCKER_TLS_VERIFY": "/custom/ca.pem"}):
            cfg = load_config()
        assert cfg.docker.tls.verify.file == "/custom/ca.pem"

    def test_docker_tls_cert_override(self):
        """DOCKER_TLS_CERT env var should override TLS cert path."""
        with patch("sys.argv", ["prog"]), \
             patch.dict(os.environ, {"DOCKER_TLS_CERT": "/custom/cert.pem"}):
            cfg = load_config()
        assert cfg.docker.tls.cert.file == "/custom/cert.pem"

    def test_docker_tls_key_override(self):
        """DOCKER_TLS_KEY env var should override TLS key path."""
        with patch("sys.argv", ["prog"]), \
             patch.dict(os.environ, {"DOCKER_TLS_KEY": "/custom/key.pem"}):
            cfg = load_config()
        assert cfg.docker.tls.key.file == "/custom/key.pem"


# ---------------------------------------------------------------------------
# CLI argument overrides
# ---------------------------------------------------------------------------


class TestCLIOverrides:
    """Tests for CLI argument overrides in load_config."""

    def test_cli_docker_host(self):
        """--docker.host CLI arg should override Docker host."""
        with patch("sys.argv", ["prog", "--docker.host", "tcp://cli:2375"]):
            cfg = load_config()
        assert cfg.docker.host == "tcp://cli:2375"

    def test_cli_traefik_containername(self):
        """--traefik.containername CLI arg should override container name."""
        with patch("sys.argv", ["prog", "--traefik.containername", "cli-traefik"]):
            cfg = load_config()
        assert cfg.traefik.containerName == "cli-traefik"

    def test_cli_overrides_env(self):
        """CLI arguments should take precedence over environment variables."""
        with patch("sys.argv", ["prog", "--docker.host", "tcp://cli:2375"]), \
             patch.dict(os.environ, {"DOCKER_HOST": "tcp://env:2375"}):
            cfg = load_config()
        assert cfg.docker.host == "tcp://cli:2375"

    def test_unknown_arg_exits(self):
        """Unknown CLI arguments should cause sys.exit(1)."""
        with patch("sys.argv", ["prog", "--nonexistent.arg", "value"]), \
             pytest.raises(SystemExit) as exc_info:
            load_config()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# init_loggers
# ---------------------------------------------------------------------------


class TestInitLoggers:
    """Tests for the init_loggers function."""

    def test_returns_logger(self):
        """init_loggers should return a Logger instance."""
        with patch("sys.argv", ["prog"]):
            cfg = load_config()
        logger = init_loggers(cfg)
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self):
        """The returned logger should be named 'application'."""
        with patch("sys.argv", ["prog"]):
            cfg = load_config()
        logger = init_loggers(cfg)
        assert logger.name == "application"

    def test_logger_level_matches_config(self):
        """Logger level should match the application log level from config."""
        with patch("sys.argv", ["prog"]):
            cfg = load_config()
        logger = init_loggers(cfg)
        assert logger.level == logging.getLevelName(cfg.logLevel.application)

    def test_propagation_disabled(self):
        """Logger propagation should be disabled to avoid duplicate messages."""
        with patch("sys.argv", ["prog"]):
            cfg = load_config()
        logger = init_loggers(cfg)
        assert logger.propagate is False
