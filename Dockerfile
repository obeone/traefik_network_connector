# Use the official Python image as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Set an argument for the version
ARG VERSION=unknown

# Copy the requirements file and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code
COPY . .

# Set the entrypoint for the container
ENTRYPOINT [ "/usr/local/bin/python", "/usr/src/app/main.py" ]

# --- Metadata ---

# Set the maintainer label
LABEL maintainer="obeone <obeone@obeone.org>"
LABEL description="Automatically connect traefik to docker's services networks which is needed"
LABEL project="traefik_network_connector"
LABEL url="https://github.com/obeone/traefik_network_connector"
LABEL vcs-url="https://github.com/obeone/traefik_network_connector"
LABEL keywords="docker, docker compose, traefik, reverse proxy, network automation, dynamic configuration, TLS support, container management"
LABEL org.opencontainers.image.source https://github.com/obeone/traefik_network_connector
LABEL org.opencontainers.image.version=$VERSION

# Set environment variable for the application version
ENV APP_VERSION=$VERSION
