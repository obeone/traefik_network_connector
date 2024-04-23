# Traefik Network Connector

This project automates the process of connecting the Traefik reverse proxy to Docker container networks dynamically. It listens for Docker events and manages Traefik's network connections to ensure it can reverse proxy for containers labeled for Traefik management.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [TLS Configuration](#tls-configuration)
- [Systemd Service Setup](#systemd-service-setup)
- [FAQs / Troubleshooting](#faqs--troubleshooting)
- [Contributing](#contributing)
- [Author](#author)

## Features

- 🌐 **Automatic Network Connection**: Automatically connects Traefik to the networks of newly created containers that are labeled for Traefik.
- 🔌 **Intelligent Network Disconnection**: Disconnects Traefik from networks of containers that are no longer running, ensuring a clean and efficient network setup.
- ⚙️ **Dynamic Configuration**: Utilizes a YAML configuration file for easy setup and adjustments without needing to alter the source code.
- 🔒 **TLS Support**: Secure your Docker API communication by specifying TLS configuration details in `config.yaml`.

## Requirements

- Docker
- Python 3.6+
- See `requirements.txt` for details.

## Installation

To get started with the Traefik Network Connector, follow these steps:

1. Clone the repository:

   ```bash
   git clone https://github.com/obeone/traefik_network_connector.git
   ```

2. Navigate to the cloned directory:

   ```bash
   cd traefik_network_connector
   ```

3. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Modify `config.yaml` to adjust the Traefik container name, the label to monitor, and other settings. Key configuration options include:

- `traefik_container_name`: Name of the Traefik container in Docker.
- `monitored_label`: Docker label that triggers network connection actions.
- `log_level`: Adjust the verbosity of the script's output.

For a detailed explanation of all configuration options, refer to the comments within `config.yaml`.

## Usage

To use the Traefik Network Connector, follow these steps:

1. Ensure Docker is running and you have the necessary permissions to interact with Docker's API.
2. Configure `config.yaml` with your Traefik container's name and desired log level.
3. Run the script:

   ```bash
   python main.py --config_path=<path_to_your_config.yaml>
   ```

   If the `--config_path` argument is omitted, the script defaults to using `config.yaml` in the current directory.

## How It Works

- **Monitoring Docker Events**: Listens for creation and destruction events of containers and manages network connections accordingly.
- **Connecting Traefik**: When a container with the specified label is created, it connects Traefik to its network if not already connected.
- **Disconnecting Traefik**: If a container is destroyed, it checks if Traefik should be disconnected from its network, based on other containers' usage of the network.

## TLS Configuration

To ensure secure communication with the Docker server, configure the following TLS settings in `config.yaml`:

```yaml
docker:
  host: "tcp://<your_docker_host>:2376"  # Replace with your Docker host and port
  tls:
    verify: "/path/to/ca.pem"  # Path to CA certificate for TLS verification
    cert: "/path/to/cert.pem"  # Path to client certificate for TLS
    key: "/path/to/key.pem"  # Path to client key for TLS
```

## Systemd Service Setup

To manage the Traefik Network Connector as a service using systemd, follow these steps:

1. Place the `traefik_network_connector.service` file in `/etc/systemd/system/`.
2. Reload the systemd daemon: `sudo systemctl daemon-reload`.
3. Start the service: `sudo systemctl start traefik_network_connector`.
4. Enable the service at boot: `sudo systemctl enable traefik_network_connector`.
5. Check the service status: `sudo systemctl status traefik_network_connector`.

## FAQs / Troubleshooting

This section addresses common issues and questions:

- **Q: How do I resolve Docker API communication errors?**
  - A: If you are using TCP connections, ensure your Docker daemon is configured to allow secure connections and that your `config.yaml` TLS settings are correct.

- **Q: What if Traefik is not connecting to a container's network?**
  - A: Verify that the container has the correct label as specified in your [config.yaml](vscode-remote://ssh-remote%2Bmy-server/root/automatic_traefik/config.yaml#1%2C1-1%2C1) and that Traefik is running. Also, check the container's network settings to ensure it's on a network that Traefik is monitoring.

- **Q: How can I debug connection issues between Traefik and Docker containers?**
  - A: Increase the `log_level` in [config.yaml](vscode-remote://ssh-remote%2Bmy-server/root/automatic_traefik/config.yaml#1%2C1-1%2C1) to `DEBUG` to get more detailed output from the script. This can provide insights into the connection process and where it might be failing.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any bugs or feature requests. Before contributing, please read through existing issues and pull requests to ensure that your contribution is unique and beneficial.

## Author

For support or queries, please open an issue on this repository. We aim to respond as quickly as possible to all inquiries.

👾 **obeone**

Primarily powered by my new brain, GPT-4, with some crucial tweaks and oversight from my secondary brain.

Check out more of my work on [GitHub](https://github.com/obeone).
