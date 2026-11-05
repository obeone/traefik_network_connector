"""
Unit tests for the monitor_events function in main.py.

Tests validate that Docker container events (start, stop, die) trigger
the correct network management actions based on container labels and
Traefik's running state.
"""

from unittest.mock import MagicMock, call, patch

import docker.errors
import pytest

import main


def make_event(action, container_id="container-123", event_type="container"):
    """
    Build a Docker event dict matching the structure returned by
    client.events(decode=True).

    Parameters
    ----------
    action : str
        The event action (start, stop, die).
    container_id : str
        The container ID included in the event.
    event_type : str
        The event Type field.

    Returns
    -------
    dict
        A minimal Docker event dictionary.
    """
    return {
        "Type": event_type,
        "Action": action,
        "id": container_id,
    }


class TestMonitorEvents:
    """Tests for the monitor_events function."""

    def _run_monitor_with_events(self, events, mock_docker_client, containers_by_id=None):
        """
        Helper that feeds a list of events into monitor_events, then stops
        iteration by raising StopIteration.

        Parameters
        ----------
        events : list[dict]
            Docker event dicts to replay.
        mock_docker_client : MagicMock
            The patched main.client.
        containers_by_id : dict, optional
            Mapping of container IDs to mock container objects for the cache.
        """
        mock_docker_client.events.return_value = iter(events)

        if containers_by_id:
            def get_side_effect(cid):
                if cid in containers_by_id:
                    return containers_by_id[cid]
                raise Exception(f"Unexpected container get: {cid}")
            mock_docker_client.containers.get.side_effect = get_side_effect

        main.monitor_events()

    def test_start_event_with_label_calls_connect(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """
        A 'start' event for a container with the monitored label should
        trigger connect_traefik_to_network.
        """
        container = MagicMock()
        container.name = "web-app"
        container.id = "web-123"
        container.labels = {"traefik.enable": "true"}
        container.attrs = {"NetworkSettings": {"Networks": {"app_net": {}}}}

        traefik = MagicMock()
        traefik.name = "traefik"
        traefik.status = "running"


        def get_container(cid):
            if cid == "web-123":
                return container
            if cid == "traefik":
                return traefik
            return MagicMock()

        mock_docker_client.containers.get.side_effect = get_container

        events = [make_event("start", "web-123")]
        mock_docker_client.events.return_value = iter(events)

        with patch.object(main, "connect_traefik_to_network") as mock_connect:
            main.container_cache.clear()
            main.monitor_events()
            mock_connect.assert_called_once_with(container)

    def test_stop_event_with_label_calls_disconnect(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """
        A 'stop' event for a labeled container should trigger
        disconnect_traefik_from_network.
        """
        container = MagicMock()
        container.name = "web-app"
        container.id = "web-123"
        container.labels = {"traefik.enable": "true"}
        container.attrs = {"NetworkSettings": {"Networks": {"app_net": {}}}}

        traefik = MagicMock()
        traefik.name = "traefik"
        traefik.status = "running"

        mock_docker_client.containers.get.side_effect = lambda cid: (
            container if cid == "web-123" else traefik
        )

        events = [make_event("stop", "web-123")]
        mock_docker_client.events.return_value = iter(events)

        with patch.object(main, "disconnect_traefik_from_network") as mock_disconnect:
            main.container_cache.clear()
            main.monitor_events()
            mock_disconnect.assert_called_once_with(container)

    def test_die_event_with_label_calls_disconnect_and_removes_cache(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """
        A 'die' event for a labeled container should trigger disconnect
        and remove the container from the cache.
        """
        container = MagicMock()
        container.name = "web-app"
        container.id = "web-123"
        container.labels = {"traefik.enable": "true"}
        container.attrs = {"NetworkSettings": {"Networks": {"app_net": {}}}}

        traefik = MagicMock()
        traefik.name = "traefik"
        traefik.status = "running"

        mock_docker_client.containers.get.side_effect = lambda cid: (
            container if cid == "web-123" else traefik
        )

        events = [make_event("die", "web-123")]
        mock_docker_client.events.return_value = iter(events)

        with patch.object(main, "disconnect_traefik_from_network") as mock_disconnect:
            main.container_cache.clear()
            main.monitor_events()
            mock_disconnect.assert_called_once_with(container)
            assert "web-123" not in main.container_cache

    def test_event_without_label_is_ignored(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """
        Events from containers without the monitored label should not
        trigger any connect/disconnect actions.
        """
        container = MagicMock()
        container.name = "plain-container"
        container.id = "plain-123"
        container.labels = {"some.other.label": "value"}
        container.attrs = {"NetworkSettings": {"Networks": {"net": {}}}}

        traefik = MagicMock()
        traefik.name = "traefik"
        traefik.status = "running"

        mock_docker_client.containers.get.side_effect = lambda cid: (
            container if cid == "plain-123" else traefik
        )

        events = [make_event("start", "plain-123")]
        mock_docker_client.events.return_value = iter(events)

        with patch.object(main, "connect_traefik_to_network") as mock_connect, \
             patch.object(main, "disconnect_traefik_from_network") as mock_disconnect:
            main.container_cache.clear()
            main.monitor_events()
            mock_connect.assert_not_called()
            mock_disconnect.assert_not_called()

    def test_events_skipped_when_traefik_not_running(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """
        When Traefik is not running, all events should be skipped
        with a warning logged.
        """
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound("gone")

        events = [make_event("start", "web-123")]
        mock_docker_client.events.return_value = iter(events)

        with patch.object(main, "connect_traefik_to_network") as mock_connect:
            main.container_cache.clear()
            main.monitor_events()
            mock_connect.assert_not_called()

    def test_healthcheck_burst_performs_no_container_requests(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """Ignored events must not trigger an inspect of every running container."""
        events = [
            make_event(action)
            for _ in range(1000)
            for action in ("exec_create: /app healthcheck", "exec_start: /app healthcheck", "exec_die")
        ]
        mock_docker_client.events.return_value = iter(events)

        main.monitor_events()

        mock_docker_client.containers.get.assert_not_called()
        mock_docker_client.containers.list.assert_not_called()
        mock_docker_client.events.assert_called_once_with(
            decode=True,
            filters={"type": "container", "event": ["start", "stop", "die"]},
        )

    @pytest.mark.parametrize("action", [
        "health_status: healthy", "health_status: unhealthy", "create", "destroy",
        "top", "exec_create", "exec_start", "unknown", None,
    ])
    def test_irrelevant_actions_perform_no_container_requests(
        self, mock_docker_client, mock_config, action
    ):
        mock_docker_client.events.return_value = iter([make_event(action)])

        main.monitor_events()

        mock_docker_client.containers.get.assert_not_called()
        mock_docker_client.containers.list.assert_not_called()

    @pytest.mark.parametrize("identity", [
        {"Actor": {"ID": "web-123"}},
        {"id": "web-123"},
        {"Actor": {"ID": "web-123"}, "id": "legacy-id"},
    ])
    def test_lifecycle_event_needs_only_two_container_reads(
        self, mock_docker_client, mock_config, identity
    ):
        traefik = MagicMock(status="running")
        container = MagicMock(id="web-123", labels={"traefik.enable": "true"})
        container.name = "web-app"
        mock_docker_client.containers.get.side_effect = {
            "traefik": traefik, "web-123": container,
        }.__getitem__
        mock_docker_client.events.return_value = iter([
            {"Type": "container", "Action": "start", **identity},
        ])

        with patch.object(main, "connect_traefik_to_network") as connect:
            main.container_cache.clear()
            main.monitor_events()
            connect.assert_called_once_with(container)

        assert mock_docker_client.containers.get.call_args_list == [
            call("traefik"), call("web-123"),
        ]
        mock_docker_client.containers.list.assert_not_called()

    def test_event_without_id_performs_no_container_requests(
        self, mock_docker_client, mock_config, mock_logger
    ):
        mock_docker_client.events.return_value = iter([
            {"Type": "container", "Action": "start"},
        ])

        main.monitor_events()

        mock_docker_client.containers.get.assert_not_called()
        mock_docker_client.containers.list.assert_not_called()
        mock_logger.warning.assert_called_once()

    @pytest.mark.parametrize("action", ["stop", "die"])
    def test_removed_container_uses_cached_network_details(
        self, mock_docker_client, mock_config, action
    ):
        traefik = MagicMock(status="running")
        container = MagicMock(id="web-123", labels={"traefik.enable": "true"})
        container.name = "web-app"

        def get_container(cid):
            if cid == "traefik":
                return traefik
            raise docker.errors.NotFound("already removed")

        mock_docker_client.containers.get.side_effect = get_container
        mock_docker_client.events.return_value = iter([make_event(action, "web-123")])
        main.container_cache.clear()
        main.container_cache[container.id] = container

        with patch.object(main, "disconnect_traefik_from_network") as disconnect:
            main.monitor_events()
            disconnect.assert_called_once_with(container)

        assert (container.id in main.container_cache) == (action == "stop")

    def test_traefik_start_event_triggers_connect_all(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """
        When Traefik itself starts, connect_to_all_relevant_networks
        should be called to re-establish all connections.
        """
        traefik = MagicMock()
        traefik.name = "traefik"
        traefik.id = "traefik-123"
        traefik.status = "running"
        traefik.labels = {"traefik.enable": "true"}
        traefik.attrs = {"NetworkSettings": {"Networks": {"bridge": {}}}}

        mock_docker_client.containers.get.side_effect = lambda cid: traefik

        events = [make_event("start", "traefik-123")]
        mock_docker_client.events.return_value = iter(events)

        with patch.object(main, "connect_to_all_relevant_networks") as mock_connect_all:
            main.container_cache.clear()
            main.monitor_events()
            mock_connect_all.assert_called_once()

    def test_non_container_events_are_ignored(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """Events with Type != 'container' should be silently skipped."""
        events = [
            {"Type": "network", "Action": "create", "id": "net-123"},
            {"Type": "volume", "Action": "create", "id": "vol-123"},
        ]
        mock_docker_client.events.return_value = iter(events)

        with patch.object(main, "connect_traefik_to_network") as mock_connect:
            main.container_cache.clear()
            main.monitor_events()
            mock_connect.assert_not_called()
