import docker
import logging
from config import config, app_logger
import re

# Function to initialize Docker client, potentially with TLS
def create_docker_client(config):
    """
    Initialize Docker client based on configuration.

    Args:
        config (dict): Configuration containing Docker client settings, potentially including TLS.

    Returns:
        docker.DockerClient: Configured Docker client instance.

    This function initializes a Docker client using settings from the provided configuration. If TLS settings are
    specified, it also configures TLS for the Docker client.
    """
    tls_config = None
    if config.docker.tls.enabled:
        tls_config = docker.tls.TLSConfig(
            client_cert=(config.docker.tls.cert, config.docker.tls.key),
            verify=config.docker.tls.verify
        )
    return docker.DockerClient(base_url=config.docker.host, tls=tls_config)

client = create_docker_client(config)


def connect_to_all_relevant_networks():
    """
    Connects Traefik to all networks of containers with the 'traefik.enable=true' label.

    This function iterates over all containers labeled 'traefik.enable=true' and connects the Traefik container to
    their networks if it's not already connected. This ensures Traefik can route traffic to these containers.
    """
    app_logger.debug("Searching for Traefik container to connect to relevant networks.")
    traefik_container = client.containers.get(config.traefik.containerName)
    traefik_nets = set(traefik_container.attrs["NetworkSettings"]["Networks"])

    for container in client.containers.list(filters={"label": "traefik.enable=true"}):
        for net in container.attrs["NetworkSettings"]["Networks"]:
            if net not in traefik_nets:
                app_logger.debug(f"Connecting Traefik to network {net}.")
                network = client.networks.get(net)
                network.connect(traefik_container)
                traefik_nets.add(net)
                app_logger.info(f"Traefik connected to network {net}.")
            else:
                app_logger.info(f"Traefik already connected to network {net}, skipping.")

def connect_traefik_to_network(container):
    """
    Connects Traefik to the network of a specified container if not already connected.

    Args:
        container (docker.models.containers.Container): Container to connect Traefik to its network.

    This function checks if Traefik is already connected to the network of the specified container. If not, it
    connects Traefik to this network to enable traffic routing.
    """
    app_logger.debug(f"Connecting Traefik to network of container {container.name}.")
    traefik_container = client.containers.get(config.traefik.containerName)
    target_networks = set(container.attrs["NetworkSettings"]["Networks"])

    for net in target_networks:
        if net not in traefik_container.attrs["NetworkSettings"]["Networks"]:
            app_logger.debug(f"Connecting Traefik to network {net}.")
            network = client.networks.get(net)
            network.connect(traefik_container)
            app_logger.info(f"Traefik connected to network {net}.")
        else:
            app_logger.info(f"Traefik already connected to network {net}, skipping.")

def disconnect_traefik_from_network(container):
    """
    Disconnects Traefik from the network of a specified container under certain conditions.

    Args:
        container (docker.models.containers.Container): Container from whose network Traefik will be disconnected.

    This function disconnects Traefik from the network of the specified container if no other running containers
    with the 'traefik.enable=true' label are using the same network and if Traefik is currently connected to that
    network. This is to ensure Traefik only remains connected to networks where it needs to route traffic.
    """
    app_logger.debug(f"Attempting to disconnect Traefik from network of container {container.name}.")
    traefik_container = client.containers.get(config.traefik.containerName)
    traefik_networks = set(traefik_container.attrs["NetworkSettings"]["Networks"])
    target_networks = set(container.attrs["NetworkSettings"]["Networks"])

    for net in target_networks:
        if net in traefik_networks:
            network = client.networks.get(net)
            # Fetch all containers connected to the network
            connected_containers = network.attrs["Containers"]
            # Filter for containers with 'traefik.enable=true' label, excluding the Traefik container itself
            relevant_containers = [cid for cid in connected_containers if client.containers.get(cid).labels.get("traefik.enable") == "true" and cid != traefik_container.id]

            # If no relevant containers are found, disconnect Traefik from the network
            if not relevant_containers:
                app_logger.debug(f"No relevant containers found on network {net}. Disconnecting Traefik.")
                network.disconnect(traefik_container)
                app_logger.info(f"Traefik disconnected from network {net}.")
            else:
                app_logger.info(f"Found relevant containers on network {net}, skipping disconnection.")
        else:
            app_logger.info(f"Traefik not connected to network {net}, skipping disconnection.")
def monitor_events():
    """
    Monitors Docker events for container creation and destruction and manages Traefik's network connections accordingly.

    This function listens to Docker events related to container creation and destruction. It connects or disconnects Traefik from relevant container networks based on the event type.
    """
    app_logger.debug("Starting Docker events monitoring.")

    # Define the Docker events to track for managing Traefik connections
    tracked_events = {
        "container": ["start", "die"],
    }

    # Listen to Docker events in real-time
    for event in client.events(decode=True):
        # Skip event handling if Traefik is not running
        traefik_running = any(container.status == "running" for container in client.containers.list() if container.name == config.traefik.containerName)
        if not traefik_running:
            app_logger.info("Traefik container is not running. Skipping event handling.")
            continue

        # Check if the event is relevant for network management
        if event["Type"] in tracked_events and event["Action"] in tracked_events[event["Type"]]:
            app_logger.debug(f"Event detected: {event['Action']} on container {event['id']}.")
            try:
                # Retrieve the container associated with the event
                container = client.containers.get(event["id"])
            except docker.errors.NotFound:
                app_logger.warning(f"Container {event['id']} not found.")
                container = None
                continue

            # Define the monitored label pattern
            monitoredLabel_pattern = re.compile(config.traefik.monitoredLabel)

            # Handle both creation and destruction events for Traefik itself
            if container.name == config.traefik.containerName:
                if event["Action"] == "start":
                    app_logger.debug(f"Container {container.name} is being created. Attempting to connect Traefik to relevant networks.")
                    connect_to_all_relevant_networks()
                elif event["Action"] == "die":
                    continue  # Skip further processing if Traefik container is stopped

            # Manage creation and destruction events for containers with the monitored label, excluding the bridge network
            # Use a regular expression to check the monitored label in the container's labels
            elif any(monitoredLabel_pattern.match(label) for label in container.labels):
                if event["Action"] == "start":
                    app_logger.info(f"Container {container.name} is being created. Attempting to connect Traefik to relevant networks.")
                    connect_traefik_to_network(container)
                    
                elif event["Action"] == "die":
                    app_logger.info(
                        f"Container {container.name} is being killed. Attempting to disconnect Traefik to relevant networks."
                    )
                    disconnect_traefik_from_network(container)

if __name__ == "__main__":
    # Connect to all relevant networks on startup
    connect_to_all_relevant_networks()

    # Start monitoring events loop‹≤
    monitor_events()
