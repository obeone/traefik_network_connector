# Traefik Automatic Docker Network Connector

This project automates the process of connecting the Traefik reverse proxy to Docker container networks dynamically. It listens for Docker events and manages Traefik's network connections to ensure it can reverse proxy for containers labeled for Traefik management.

This is useful if you have, for example, one traefik proxy which handle incoming requests for multiple docker compose services. It will only to the needed networks (ie the one whith traefik labels) without the need of a common traefik network for all services, which break the isolation principal.

## Table of Contents

- [Traefik Automatic Docker Network Connector](#traefik-automatic-docker-network-connector)
  - [Table of Contents](#table-of-contents)
  - [Features](#features)
  - [Requirements](#requirements)
  - [Usage](#usage)
  - [Configuration](#configuration)
    - [Configuration File](#configuration-file)
    - [Command Line Arguments](#command-line-arguments)
    - [Environment Variables](#environment-variables)
  - [Usage as a system daemon](#usage-as-a-system-daemon)
    - [Installation](#installation)
    - [Running](#running)
    - [Systemd Service Setup](#systemd-service-setup)
  - [Docker socket proxy setup](#docker-socket-proxy-setup)
  - [How It Works](#how-it-works)
  - [TLS Configuration](#tls-configuration)
  - [FAQs / Troubleshooting](#faqs--troubleshooting)
  - [Contributing](#contributing)
  - [Author](#author)

## Features

- 🌐 **Automatic Network Connection**: Automatically connects Traefik to the networks of newly created containers that are labeled for Traefik. Ability to indicate which networks to connect to.
- 🔌 **Intelligent Network Disconnection**: Disconnects Traefik from networks of containers that are no longer running, ensuring a clean and efficient network setup.
- ⚙️ **Dynamic Configuration**: Utilizes a YAML configuration file, CLI arguments and/or environment variables for easy setup and adjustments without needing to alter the source code.
- 🔒 **TLS Support**: Secure your Docker API communication by specifying TLS configuration details.
- 🐳 **Run in cohtainer**: Run this tool directly as a container to easy integration in your project.

## Requirements

- Docker

If you want to run it outside containers, make sure you have the following installed:

- Python 3.6+
- See `requirements.txt` for details.

## Usage

Start the container :

```bash
docker run -d \
  --name traefik_network_connector \
  -v $PWD/config.yaml:/usr/src/app/config.yaml \
  -v /var/run/docker.sock:/var/run/docker.sock \
  obeoneorg/traefik_network_connector:latest
```

And it's ok !

For more details about the configuration options, refer to the [Configuration](#configuration) section.

## Configuration

### Configuration File

Modify `config.yaml` to adjust the Traefik container name, the label to monitor, and other settings. Key configuration options include:

- `traefik.containerName`: Name of the Traefik container in Docker.
- `logLevel`: Adjust the verbosity of the script's output.
- `traefik.monitoredLabel`: Docker label that triggers network connection actions. (DEPRECATED ! Directly use `traefik.docker.network` instead in Traefik 2.0+)

> :warning: **Take care !**
> @ If you use `traefik.monitoredLabel`, you just have to give the network name in your compose file.
> But if you use `traefik.docker.network`, you need to prefix the network name (for the example, let's say `mynetwork`) with your deployment name (for example, you run `docker compose up` in a directory named `foo`, your network name will be `foo_mynetwork`).
> I don't understand why me, a single developer without special knowledge about docker, I was able to detect the compose name, but not Traefik...
> So you can't use a same compose for multiple deployment, it's kind of ridiculous, but I didn't find an elegant solution... (Il you have an idea, contact me !)

For a detailed explanation of all configuration options, refer to the comments within `config.yaml`.

### Command Line Arguments

To override the default configuration settings, use the command line arguments using the `--key=value` (key is the YAML path) format. The YAML path is used to access the corresponding value in the configuration. For example, to override the log level, use the `--loglevel=INFO` argument. For the docker host, use the `--docker.host` argument.

List of available command line arguments can be found using `--help`, and explaination in the `config.yaml` file.

### Environment Variables

To override the default configuration settings, you can also use the environment variables (as for command line arguments above, key is the YAML path but using `_` instead of `.`). For example, to override the docker host, use the `DOCKER_HOST` environment variable.

## Usage as a system daemon

### Installation

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

### Running

To use the Traefik Automatic Docker Network Connector, follow these steps:

1. Ensure Docker is running and you have the necessary permissions to interact with Docker's API.
2. Configure settings [the way you like](#configuration).
3. Run the script:

   ```bash
   python main.py --config=<path_to_your_config.yaml>
   ```

   If the `--config` argument is omitted, the script defaults to using `config.yaml` in the current directory.

### Systemd Service Setup

To manage the Traefik Automatic Docker Network Connector as a service using systemd, follow these steps:

1. Place the `traefik_network_connector.service` file in `/etc/systemd/system/`.
2. Reload the systemd daemon: `sudo systemctl daemon-reload`.
3. Start the service: `sudo systemctl start traefik_network_connector`.
4. Enable the service at boot: `sudo systemctl enable traefik_network_connector`.
5. Check the service status: `sudo systemctl status traefik_network_connector`.

## Docker socket proxy setup

For increased security a Docker Socket proxy like [linuxserver/socket-proxy](https://github.com/linuxserver/docker-socket-proxy/pkgs/container/socket-proxy)
can be used.

Essential configuration using Docker Compose:

```yaml
services:
  traefik-network-connector:
    image: obeoneorg/traefik_network_connector:...
    depends_on:
      traefik-network-connector-docker-proxy:
        condition: service_healthy
    environment:
      DOCKER_HOST: tcp://traefik-network-connector-docker-proxy:2375
    networks:
      - traefik-network-connector-docker-proxy

  traefik-network-connector-docker-proxy:
    environment:
      CONTAINERS: 1
      NETWORKS: 1
      POST: 1
    networks:
      - traefik-network-connector-docker-proxy

networks:
  traefik-network-connector-docker-proxy:
    name: traefik-network-connector-docker-proxy
    internal: true
```

The Traefik Automatic Docker Network Connector needs read access to the `containers` (`CONTAINERS: 1`)
and `networks` (`NETWORKS: 1`) API as well as write permissions (`POST: 1`). In case the Docker socket
proxy exposes the Docker API via TCP, the Docker host must be configured accordingly.

## How It Works

- **Monitoring Docker Events**: Listens for creation and destruction events of containers and manages network connections accordingly.
- **Connecting Traefik**: When a container with the specified label is created, it connects Traefik to its network if not already connected. If a config specified label is present (default is `autoproxy.networks`) only these networks will be connected to.
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

## FAQs / Troubleshooting

This section addresses common issues and questions:

- **Q: How do I resolve Docker API communication errors?**
  - A: If you are using TCP connections, ensure your Docker daemon is configured to allow secure connections and that your `config.yaml` (or CLI/Environment variable) TLS settings are correct.

- **Q: What if Traefik is not connecting to a container's network?**
  - A: Verify that the container has the correct label to be monitored as specified in your config.yaml and that Traefik is running an its name is properly set in your configuration. Also, check the logs.

- **Q: How can I debug connection issues between Traefik and Docker containers?**
  - A: Increase the `logLevel`to `DEBUG` to get more detailed output from the script. This can provide insights into the connection process and where it might be failing.

- **Q: How do I override configuration settings?**
  - **A:** You can override settings using command line arguments as detailed in the Usage section. Each configuration in `config.yaml` can be overridden by an equivalent command line argument or environment variable, see [Configuration Settings](#configuration).

- **Q: What is the priority for configuration settings?**
  - **A:** Command line arguments have the highest priority, followed by environment variables, and then the default settings in `config.yaml`.

- **Q: How can I debug issues with incorrect configuration values?**
  - **A:** Ensure that your command line arguments and environment variables are correctly formatted and match the expected patterns. Use the `--help` option with the script to see available command line arguments.

- **Q: How can I specify the networks Traefik should connect to?**
  - **A:** It was easy, but... Look at [Configuration](#configuration).

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any bugs or feature requests. Before contributing, please read through existing issues and pull requests to ensure that your contribution is unique and beneficial.

## Author

For support or queries, please open an issue on this repository. We aim to respond as quickly as possible to all inquiries.

👾 **obeone**

Primarily powered by my new brain, GPT-4o, with some crucial tweaks and oversight from my secondary brain.

Check out more of my work on [GitHub](https://github.com/obeone).
