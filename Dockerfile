FROM python:3.12-slim

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENTRYPOINT [ "/usr/local/bin/python", "/usr/src/app/main.py" ]


LABEL maintainer="obeone <obeone@obeone.org>"
LABEL description="Automatically connect traefik to docker's services networks which is needed"
LABEL project="traefik_network_connector"
LABEL url="https://github.com/obeone/traefik_network_connector"
LABEL vcs-url="https://github.com/obeone/traefik_network_connector"
LABEL keywords="docker, docker compose, traefik, reverse proxy, network automation, dynamic configuration, TLS support, container management"
LABEL org.opencontainers.image.source https://github.com/obeone/traefik_network_connector
