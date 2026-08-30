"""
Unit tests for the monitor_events function in main.py.

Tests validate that Docker container events (start, stop, die) trigger
the correct network management actions based on container labels and
Traefik's running state.
"""

from unittest.mock import MagicMock, call, patch

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

        mock_docker_client.containers.list.return_value = [traefik]

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

    def test_start_event_with_label_key_but_wrong_value_is_skipped(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """
        Docker's server-side "label" event filter only matches on the label key, not its value
        (there is no way to express monitoredLabelCondition in that filter). A container carrying
        the label with a non-matching value (e.g. traefik.enable=false) must therefore still be
        rejected in application code instead of triggering a connect.
        """
        container = MagicMock()
        container.name = "web-app"
        container.id = "web-123"
        container.labels = {"traefik.enable": "false"}
        container.attrs = {"NetworkSettings": {"Networks": {"app_net": {}}}}

        traefik = MagicMock()
        traefik.name = "traefik"
        traefik.status = "running"

        mock_docker_client.containers.list.return_value = [traefik]

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
            mock_connect.assert_not_called()

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

        mock_docker_client.containers.list.return_value = [traefik]
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

        mock_docker_client.containers.list.return_value = [traefik]
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

        mock_docker_client.containers.list.return_value = [traefik]
        mock_docker_client.containers.get.side_effect = lambda cid: (
            container if cid == "plain-123" else MagicMock()
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
        mock_docker_client.containers.list.return_value = []

        events = [make_event("start", "web-123")]
        mock_docker_client.events.return_value = iter(events)

        with patch.object(main, "connect_traefik_to_network") as mock_connect:
            main.container_cache.clear()
            main.monitor_events()
            mock_connect.assert_not_called()

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

        mock_docker_client.containers.list.return_value = [traefik]
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


class TestWatchTraefikEventsOnce:
    """
    Tests for watch_traefik_events_once(), the single-pass subscription logic behind
    monitor_traefik_events() (which wraps it in an infinite retry loop and is therefore not itself
    directly unit-testable -- it never returns by design).

    Regression coverage for the case flagged in review: a Traefik restart must still trigger
    connect_to_all_relevant_networks() even when the Traefik container does NOT carry the
    monitoredLabel (the common case, since Traefik has no need to route to itself). The
    label-filtered monitor_events() subscription alone cannot observe that event, since Docker
    filters it out server-side.
    """

    def test_traefik_start_triggers_connect_all_without_label(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """A 'start' event on the Traefik container reconnects all networks, label or not."""
        events = [make_event("start", "traefik-123")]
        mock_docker_client.events.return_value = iter(events)

        with patch.object(main, "connect_to_all_relevant_networks") as mock_connect_all:
            main.watch_traefik_events_once()
            mock_connect_all.assert_called_once()

    def test_subscribes_with_container_filter_not_label(
        self, mock_docker_client, mock_config, mock_logger
    ):
        """The dedicated subscription must filter by container name, not by monitoredLabel."""
        mock_docker_client.events.return_value = iter([])

        main.watch_traefik_events_once()

        _, kwargs = mock_docker_client.events.call_args
        assert kwargs["filters"]["container"] == [mock_config.traefik.containerName]
        assert "label" not in kwargs["filters"]


class TestMonitorTraefikEventsRetry:
    """
    Tests that monitor_traefik_events() (the retry wrapper around watch_traefik_events_once())
    survives a failure instead of letting the background thread die silently -- the daemon thread
    has no supervisor, so an uncaught exception here would otherwise permanently and silently stop
    Traefik from reconnecting on restart, with nothing else signaling the problem.
    """

    def test_retries_after_failure_instead_of_propagating(self, mock_logger):
        """A failure in one pass must be logged and retried after a delay, not left to propagate."""
        call_count = {"n": 0}

        def flaky_watch():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("transient failure")
            # Sentinel to escape the infinite retry loop once the retry has been observed.
            # SystemExit subclasses BaseException, not Exception, so it isn't swallowed by the
            # subscription's own "except Exception" handler.
            raise SystemExit

        with patch.object(main, "watch_traefik_events_once", side_effect=flaky_watch), \
             patch("main.time.sleep") as mock_sleep, \
             pytest.raises(SystemExit):
            main.monitor_traefik_events()

        assert call_count["n"] == 2
        mock_sleep.assert_called_once_with(5)
