import docker
import logging
from config import config, app_logger
import re

# Initialize the cache for container details
container_cache = {}

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


def update_container_cache(container_or_id):
    """
    Tries to get container details from Docker and updates the cache with the latest details.

    This function attempts to retrieve a container using its ID or container object and updates the cache with its latest details.
    The cache is a dictionary where the key is the container ID and the value is a dictionary
    containing the container's networks, status, and labels. If the container cannot be retrieved,
    the cache is not updated.

    Args:
        container_or_id (str or docker.models.containers.Container): Container object or ID of the container to update in the cache.
    """
    try:
        container = client.containers.get(container_or_id) if isinstance(container_or_id, str) else container_or_id
        
        if container is None:
            app_logger.warning(f"Container {container_or_id} not found. Skipping cache update.")
            return

        app_logger.debug(f"Updating container cache for container {container.name}.")

        container_cache[container.id] = container
    except docker.errors.NotFound:
        pass  # Container not found; do not update cache

def connect_to_all_relevant_networks():
    """
    Connects Traefik to all networks of containers with the 'traefik.enable=true' label and ensures connection only to networks specified in the 'traefik.networkLabel' label if present.

    This function iterates over all containers labeled 'traefik.enable=true'. If the container has a 'traefik.networkLabel' label, it checks if the network is listed in the label's value before connecting the Traefik container to their networks if it's not already connected. This ensures Traefik can route traffic to these containers.
    """
    if not is_traefik_running():
        app_logger.warning("Traefik is not running. Skipping network connection.")
        return
    
    app_logger.debug("Searching for Traefik container to connect to relevant networks.")
    
    for container in client.containers.list(filters={"label": "traefik.enable=true"}):
        update_container_cache(container)
        connect_traefik_to_network(container)
    
    app_logger.debug("Finished searching for Traefik container to connect to relevant networks.")

def connect_traefik_to_network(container):
    """
    Connects Traefik to the network of a specified container if not already connected, considering the 'traefik.networkLabel' for allowed networks, and accounting for external networks.

    Args:
        container (docker.models.containers.Container): Container to connect Traefik to its network.

    This function checks if Traefik is already connected to the network of the specified container. If not, it
    connects Traefik to this network to enable traffic routing. It also checks if the 'traefik.networkLabel' is present
    on the container and if so, only connects to the networks listed in this label. Additionally, it accounts for
    external networks in network names.
    """
    app_logger.debug(f"Attempting to connect Traefik to the network of container {container.name}.")
    # Retrieve the Traefik container based on configuration
    traefik_container = client.containers.get(config.traefik.containerName)
    # Determine the target networks of the specified container
    target_networks = set(container.attrs["NetworkSettings"]["Networks"].keys())
    # Retrieve allowed networks from the container's labels, if specified
    allowed_networks_label = container.labels.get(config.traefik.networkLabel, "")
    allowed_networks = allowed_networks_label.split(",")
    
    app_logger.debug(f"Allowed networks: {allowed_networks}")

    for net in target_networks:
        # Attempt to retrieve the network object; checks for external networks by matching labels
        network = client.networks.get(net)
        
        if container.labels.get('com.docker.compose.project') and 'com.docker.compose.project' in network.attrs['Labels']:
            if container.labels.get('com.docker.compose.project') == network.attrs['Labels']['com.docker.compose.project'] and network.attrs['Labels']['com.docker.compose.network']  in allowed_networks:
                app_logger.debug(f"Network {network.attrs['Name']} corresponds to a docker compose network described in the allowed networks.")
            
                # Construct the real network name for Docker Compose projects
                real_network = f"{network.attrs['Labels']['com.docker.compose.project']}_{network.attrs['Labels']['com.docker.compose.network']}"
                # Determine if the network is listed in the allowed networks, adjusting the list as necessary
                index_allowed = allowed_networks.index(network.attrs['Labels']['com.docker.compose.network']) if network.attrs['Labels']['com.docker.compose.network'] in allowed_networks else -1
                
                if index_allowed >= 0:
                    allowed_networks[index_allowed] = real_network
                    app_logger.debug(f"Adjusted allowed network to {real_network}.")
        
        # Connect Traefik to the network if allowed, or log that it's skipping the connection
        if allowed_networks == [''] or net in allowed_networks:
            if net not in traefik_container.attrs["NetworkSettings"]["Networks"]:
                app_logger.debug(f"Connecting Traefik to network {net}.")
                network.connect(traefik_container)
                app_logger.info(f"Successfully connected Traefik to network {net}.")
            else:
                app_logger.info(f"Traefik is already connected to network {net}, skipping connection.")
        else:
            app_logger.info(f"Network {net} is not listed in allowed networks, skipping connection.")

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
            # Some containers may be destroyed since we got the list, so we don't do errors on them
            relevant_containers = []
            for cid in connected_containers:
                try:
                    container_to_check = client.containers.get(cid)
                    if container_to_check.labels.get("traefik.enable") == "true" and cid != traefik_container.id and cid != container.id:
                        relevant_containers.append(cid)
                except docker.errors.NotFound:
                    continue
                
            # If no relevant containers are found, disconnect Traefik from the network
            if not relevant_containers:
                app_logger.debug(f"No relevant containers found on network {net}. Disconnecting Traefik.")
                network.disconnect(traefik_container)
                app_logger.info(f"Traefik disconnected from network {net}.")
            else:
                app_logger.info(f"Found relevant containers on network {net}, skipping disconnection.")
        else:
            app_logger.info(f"Traefik not connected to network {net}, skipping disconnection.")

def is_traefik_running():
    """
    Checks if Traefik container is running.

    Returns:
        bool: True if Traefik container is running, False otherwise.
    """
    traefik_running = any(container.status == "running" for container in client.containers.list() if container.name == config.traefik.containerName)
    return traefik_running

def monitor_events():
    """
    Monitors Docker events for container creation and destruction and manages Traefik's network connections accordingly.

    This function listens to Docker events related to container creation and destruction. It connects or disconnects Traefik from relevant container networks based on the event type.
    """
    app_logger.debug("Starting Docker events monitoring.")

    # Define the Docker events to track for managing Traefik connections
    tracked_events = {
        "container": ["start", "stop", "die"],
    }

    # Listen to Docker events in real-time
    for event in client.events(decode=True):
        # Filter out events that are not related to container creation/destruction
        if event.get('Type') != 'container':
            continue
        
        if not is_traefik_running():
            app_logger.warning("Traefik is not running. Skipping event handling.")
            continue

        # Update the container cache on every container event (can be manual connection to network for example)
        update_container_cache(event["id"])

        # Check if the event is relevant for network management
        if event["Type"] in tracked_events and event["Action"] in tracked_events[event["Type"]]:
            # Fetch the container from the cache or None if not found
            container = container_cache[event["id"]] if event["id"] in container_cache else None

            app_logger.debug(f"Event detected: {event['Action']} on container {container.name if container else event['id']} with ID {event['id']}.")

            # Skip further processing if the container is not found or Traefik is not running
            if container is None:
                app_logger.warning(f"Container {event['id']} not found. Skipping event handling.")
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

                elif event["Action"] == "stop":
                    app_logger.info(
                        f"Container {container.name} is being stopped. Attempting to disconnect Traefik from relevant networks."
                    )
                    disconnect_traefik_from_network(container)

                elif event["Action"] == "die":
                    app_logger.info(
                        f"Container {container.name} is being killed. Attempting to disconnect Traefik from relevant networks."
                    )
                    disconnect_traefik_from_network(container)
                    del container_cache[event["id"]]

if __name__ == "__main__":
    # Connect to all relevant networks on startup
    connect_to_all_relevant_networks()

    # Start monitoring events loop‹≤
    monitor_events()
