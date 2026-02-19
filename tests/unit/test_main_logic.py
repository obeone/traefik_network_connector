"""
Unit tests for main.py logic functions.

Tests cover Docker client creation, container cache management,
network connect/disconnect logic, and Traefik status detection.
All Docker SDK interactions are mocked.
"""

from unittest.mock import MagicMock, patch, PropertyMock

import docker.errors
import pytest

import main
from tests.conftest import make_test_config


# ---------------------------------------------------------------------------
# create_docker_client
# ---------------------------------------------------------------------------


class TestCreateDockerClient:
    """Tests for the create_docker_client function."""

    @patch("main.docker.DockerClient")
    def test_without_tls(self, mock_docker_cls):
        """
        When TLS is disabled, DockerClient should be called with
        base_url only and tls=None.
        """
        cfg = make_test_config()
        main.create_docker_client(cfg)
        mock_docker_cls.assert_called_once_with(
            base_url="unix:///var/run/docker.sock", tls=None
        )

    @patch("main.docker.tls.TLSConfig")
    @patch("main.docker.DockerClient")
    def test_with_tls(self, mock_docker_cls, mock_tls_config_cls):
        """
        When TLS is enabled, a TLSConfig should be created and
        passed to DockerClient.
        """
        cfg = make_test_config()
        # Build a TLS-enabled config
        tls_enabled = cfg.docker.tls._replace(enabled=True)
        docker_cfg = cfg.docker._replace(tls=tls_enabled)
        cfg = cfg._replace(docker=docker_cfg)

        mock_tls_instance = MagicMock()
        mock_tls_config_cls.return_value = mock_tls_instance

        main.create_docker_client(cfg)

        mock_tls_config_cls.assert_called_once_with(
            client_cert=(cfg.docker.tls.cert, cfg.docker.tls.key),
            verify=cfg.docker.tls.verify,
        )
        mock_docker_cls.assert_called_once_with(
            base_url=cfg.docker.host, tls=mock_tls_instance
        )


# ---------------------------------------------------------------------------
# update_container_cache
# ---------------------------------------------------------------------------


class TestUpdateContainerCache:
    """Tests for the update_container_cache function."""

    def test_updates_cache_with_container_object(self, mock_docker_client, mock_config, mock_logger):
        """Passing a container object should store it in the cache."""
        container = MagicMock()
        container.id = "abc123"
        container.name = "test-container"

        main.container_cache.clear()
        main.update_container_cache(container)

        assert "abc123" in main.container_cache
        assert main.container_cache["abc123"] is container

    def test_updates_cache_with_string_id(self, mock_docker_client, mock_config, mock_logger):
        """Passing a string ID should fetch the container and cache it."""
        container = MagicMock()
        container.id = "abc123"
        container.name = "test-container"
        mock_docker_client.containers.get.return_value = container

        main.container_cache.clear()
        main.update_container_cache("abc123")

        mock_docker_client.containers.get.assert_called_once_with("abc123")
        assert "abc123" in main.container_cache

    def test_not_found_is_silenced(self, mock_docker_client, mock_config, mock_logger):
        """docker.errors.NotFound should be caught silently."""
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound("gone")

        main.container_cache.clear()
        main.update_container_cache("missing-id")

        assert "missing-id" not in main.container_cache


# ---------------------------------------------------------------------------
# is_traefik_running
# ---------------------------------------------------------------------------


class TestIsTraefikRunning:
    """Tests for the is_traefik_running function."""

    def test_traefik_running(self, mock_docker_client, mock_config):
        """Should return True when a running container named 'traefik' exists."""
        traefik = MagicMock()
        traefik.name = "traefik"
        traefik.status = "running"
        mock_docker_client.containers.list.return_value = [traefik]

        assert main.is_traefik_running() is True

    def test_traefik_not_running(self, mock_docker_client, mock_config):
        """Should return False when no container named 'traefik' is running."""
        other = MagicMock()
        other.name = "other-container"
        other.status = "running"
        mock_docker_client.containers.list.return_value = [other]

        assert main.is_traefik_running() is False

    def test_traefik_stopped(self, mock_docker_client, mock_config):
        """Should return False when the traefik container exists but is not running."""
        traefik = MagicMock()
        traefik.name = "traefik"
        traefik.status = "exited"
        mock_docker_client.containers.list.return_value = [traefik]

        assert main.is_traefik_running() is False


# ---------------------------------------------------------------------------
# connect_traefik_to_network
# ---------------------------------------------------------------------------


class TestConnectTraefikToNetwork:
    """Tests for the connect_traefik_to_network function."""

    def test_connects_to_new_network(self, mock_docker_client, mock_config, mock_logger):
        """
        Traefik should be connected to a network it is not already on
        when no allowed-networks label restricts it.
        """
        container = MagicMock()
        container.name = "web-app"
        container.attrs = {
            "NetworkSettings": {"Networks": {"app_net": {}}}
        }
        container.labels = {}

        traefik = MagicMock()
        traefik.attrs = {"NetworkSettings": {"Networks": {"bridge": {}}}}
        mock_docker_client.containers.get.return_value = traefik

        network = MagicMock()
        network.attrs = {"Name": "app_net", "Labels": {}}
        mock_docker_client.networks.get.return_value = network

        main.connect_traefik_to_network(container)

        network.connect.assert_called_once_with(traefik)

    def test_skips_already_connected_network(self, mock_docker_client, mock_config, mock_logger):
        """Traefik should not reconnect to a network it is already on."""
        container = MagicMock()
        container.name = "web-app"
        container.attrs = {
            "NetworkSettings": {"Networks": {"app_net": {}}}
        }
        container.labels = {}

        traefik = MagicMock()
        traefik.attrs = {"NetworkSettings": {"Networks": {"app_net": {}}}}
        mock_docker_client.containers.get.return_value = traefik

        network = MagicMock()
        network.attrs = {"Name": "app_net", "Labels": {}}
        mock_docker_client.networks.get.return_value = network

        main.connect_traefik_to_network(container)

        network.connect.assert_not_called()

    def test_skips_non_allowed_network(self, mock_docker_client, mock_config, mock_logger):
        """
        When traefik.docker.network label is set, networks not in the
        allowed list should be skipped.
        """
        container = MagicMock()
        container.name = "web-app"
        container.attrs = {
            "NetworkSettings": {"Networks": {"forbidden_net": {}}}
        }
        container.labels = {"traefik.docker.network": "allowed_net"}

        traefik = MagicMock()
        traefik.attrs = {"NetworkSettings": {"Networks": {"bridge": {}}}}
        mock_docker_client.containers.get.return_value = traefik

        network = MagicMock()
        network.attrs = {"Name": "forbidden_net", "Labels": {}}
        mock_docker_client.networks.get.return_value = network

        main.connect_traefik_to_network(container)

        network.connect.assert_not_called()

    def test_compose_network_resolution(self, mock_docker_client, mock_config, mock_logger):
        """
        Docker Compose networks should be resolved to their real name
        (project_network) and matched against the allowed networks label.
        """
        container = MagicMock()
        container.name = "web-app"
        container.attrs = {
            "NetworkSettings": {"Networks": {"myproject_web": {}}}
        }
        container.labels = {
            "traefik.docker.network": "web",
            "com.docker.compose.project": "myproject",
        }

        traefik = MagicMock()
        traefik.attrs = {"NetworkSettings": {"Networks": {"bridge": {}}}}
        mock_docker_client.containers.get.return_value = traefik

        network = MagicMock()
        network.attrs = {
            "Name": "myproject_web",
            "Labels": {
                "com.docker.compose.project": "myproject",
                "com.docker.compose.network": "web",
            },
        }
        mock_docker_client.networks.get.return_value = network

        main.connect_traefik_to_network(container)

        network.connect.assert_called_once_with(traefik)


# ---------------------------------------------------------------------------
# disconnect_traefik_from_network
# ---------------------------------------------------------------------------


class TestDisconnectTraefikFromNetwork:
    """Tests for the disconnect_traefik_from_network function."""

    def test_disconnects_when_no_other_labeled_containers(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """
        Traefik should be disconnected from a network when no other
        containers with traefik.enable=true remain.
        """
        container = MagicMock()
        container.name = "web-app"
        container.id = "web-app-id"
        container.attrs = {
            "NetworkSettings": {"Networks": {"app_net": {}}}
        }

        traefik = MagicMock()
        traefik.id = "traefik-id"
        traefik.labels = {}
        traefik.attrs = {
            "NetworkSettings": {"Networks": {"app_net": {}, "bridge": {}}}
        }

        network = MagicMock()
        # Only traefik and the stopped container are on the network
        network.attrs = {"Containers": {"traefik-id": {}, "web-app-id": {}}}
        mock_docker_client.networks.get.return_value = network

        def get_container(cid):
            if cid == "traefik":
                return traefik
            if cid == "traefik-id":
                # During the loop, traefik is checked — no traefik.enable label
                return traefik
            if cid == "web-app-id":
                # The stopped container has the label but is excluded (cid == container.id)
                c = MagicMock()
                c.labels = {"traefik.enable": "true"}
                return c
            return MagicMock()

        mock_docker_client.containers.get.side_effect = get_container

        main.disconnect_traefik_from_network(container)

        network.disconnect.assert_called_once_with(traefik)

    def test_skips_disconnect_when_other_labeled_containers_exist(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """
        Traefik should stay connected if other traefik.enable=true
        containers are still on the network.
        """
        container = MagicMock()
        container.name = "web-app"
        container.id = "web-app-id"
        container.attrs = {
            "NetworkSettings": {"Networks": {"shared_net": {}}}
        }

        traefik = MagicMock()
        traefik.id = "traefik-id"
        traefik.attrs = {
            "NetworkSettings": {"Networks": {"shared_net": {}}}
        }

        other = MagicMock()
        other.id = "other-id"
        other.labels = {"traefik.enable": "true"}

        network = MagicMock()
        network.attrs = {
            "Containers": {
                "traefik-id": {},
                "web-app-id": {},
                "other-id": {},
            }
        }

        def get_container(cid):
            if cid == "traefik":
                return traefik
            if cid == "traefik-id":
                return MagicMock(labels={})
            if cid == "other-id":
                return other
            if cid == "web-app-id":
                return MagicMock(labels={"traefik.enable": "true"})
            return MagicMock()

        mock_docker_client.containers.get.side_effect = get_container
        mock_docker_client.networks.get.return_value = network

        main.disconnect_traefik_from_network(container)

        network.disconnect.assert_not_called()

    def test_not_found_container_does_not_crash(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """
        docker.errors.NotFound during container check should be caught
        and not crash the function.
        """
        container = MagicMock()
        container.name = "web-app"
        container.id = "web-app-id"
        container.attrs = {
            "NetworkSettings": {"Networks": {"app_net": {}}}
        }

        traefik = MagicMock()
        traefik.id = "traefik-id"
        traefik.attrs = {
            "NetworkSettings": {"Networks": {"app_net": {}}}
        }

        network = MagicMock()
        network.attrs = {
            "Containers": {"traefik-id": {}, "ghost-id": {}}
        }

        def get_container(cid):
            if cid == "traefik":
                return traefik
            if cid == "traefik-id":
                return MagicMock(labels={})
            raise docker.errors.NotFound("gone")

        mock_docker_client.containers.get.side_effect = get_container
        mock_docker_client.networks.get.return_value = network

        # Should not raise
        main.disconnect_traefik_from_network(container)

        network.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# connect_to_all_relevant_networks
# ---------------------------------------------------------------------------


class TestConnectToAllRelevantNetworks:
    """Tests for the connect_to_all_relevant_networks function."""

    def test_skips_when_traefik_not_running(self, mock_docker_client, mock_config, mock_logger):
        """Should do nothing if Traefik is not running."""
        mock_docker_client.containers.list.return_value = []

        main.connect_to_all_relevant_networks()

        # containers.list is called by is_traefik_running, not for filtering
        # No network connections should happen
        mock_docker_client.networks.get.assert_not_called()

    def test_connects_to_all_labeled_containers(self, mock_docker_client, mock_config, mock_logger):
        """
        Should iterate over all containers with traefik.enable=true
        and call connect_traefik_to_network for each.
        """
        traefik = MagicMock()
        traefik.name = "traefik"
        traefik.status = "running"

        container1 = MagicMock()
        container1.name = "app1"
        container1.id = "app1-id"
        container1.attrs = {"NetworkSettings": {"Networks": {"net1": {}}}}
        container1.labels = {}

        container2 = MagicMock()
        container2.name = "app2"
        container2.id = "app2-id"
        container2.attrs = {"NetworkSettings": {"Networks": {"net2": {}}}}
        container2.labels = {}

        # is_traefik_running check
        def list_side_effect(**kwargs):
            if kwargs.get("filters", {}).get("label") == "traefik.enable=true":
                return [container1, container2]
            return [traefik]

        mock_docker_client.containers.list.side_effect = list_side_effect

        traefik_detail = MagicMock()
        traefik_detail.attrs = {"NetworkSettings": {"Networks": {"bridge": {}}}}

        def get_container(name):
            if name == "traefik":
                return traefik_detail
            return MagicMock()

        mock_docker_client.containers.get.side_effect = get_container

        network = MagicMock()
        network.attrs = {"Name": "net1", "Labels": {}}
        mock_docker_client.networks.get.return_value = network

        main.connect_to_all_relevant_networks()

        # connect should have been called for both containers' networks
        assert network.connect.call_count == 2
