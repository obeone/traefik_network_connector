# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**auto_docker_proxy** (aka Traefik Network Connector) is a Python daemon that dynamically connects/disconnects the Traefik reverse proxy to Docker container networks. It monitors Docker events in real-time and manages network connections for containers labeled `traefik.enable=true`, eliminating the need for a shared Docker network across all stacks.

## Build & Run Commands

```bash
# Docker build
docker build --build-arg VERSION=$(cat VERSION) -t obeoneorg/traefik_network_connector .

# Docker Compose (dev/demo with Traefik included)
VERSION=$(cat VERSION) docker compose up --build

# Local run (requires Python 3.6+ and Docker socket access)
pip install -r requirements.txt
python main.py
python main.py --config=/path/to/config.yaml
python main.py --traefik.containername=mytraefik --loglevel.application=DEBUG

# Tests (pytest)
pytest tests/
pytest tests/unit/
pytest tests/integration/

# Version bump + tag
./scripts/bump-version.sh [major|minor|patch]
```

## Architecture

The entire application is two Python files:

- **`main.py`** — All runtime logic: Docker client creation, event monitoring loop, network connect/disconnect logic, container cache management.
- **`config.py`** — Configuration loading with three-layer priority: `config.yaml` defaults < environment variables < CLI arguments. Uses `NamedTuple` types (`Config`, `DockerConfig`, `TraefikConfig`, etc.).

### Core Flow

1. **Startup**: Creates Docker client, scans all running containers, connects Traefik to networks of containers with `traefik.enable=true` label.
2. **Event loop** (`monitor_events()`): Listens to Docker container events:
   - `start`: If Traefik itself starts → reconnect to all relevant networks. If labeled container starts → connect Traefik to its network.
   - `stop`/`die`: If labeled container stops → disconnect Traefik from its network only if no other labeled containers remain on it.
3. **Container cache** (`container_cache` dict): Stores container objects by ID so they can be referenced on `stop`/`die` events when the container API may no longer return them.

### Key Labels

- `traefik.enable` (regex-matched via `traefik.monitoredLabel` config) — triggers network connection
- `traefik.docker.network` — specifies which network(s) Traefik should connect to for a container

## Configuration

Three-layer priority (lowest to highest): `config.yaml` → environment variables → CLI arguments.

Environment variables use `_` as separator (e.g., `DOCKER_HOST`, `TRAEFIK_CONTAINERNAME`). CLI arguments use `.` separator with `--` prefix (e.g., `--docker.host`, `--traefik.containername`).

## Versioning & CI/CD

- Version tracked in `VERSION` file (SemVer format)
- `scripts/bump-version.sh` increments version, commits, and creates git tag
- `scripts/generate-tags.sh` generates Docker tags from a SemVer git tag
- CI builds multi-platform images (`amd64`, `arm64`, `i386`, `arm/v7`) and pushes to both GHCR and Docker Hub under two names: `auto_docker_proxy` and `traefik_network_connector`
- Releases are triggered by pushing `vX.Y.Z` tags

## Dependencies

Minimal: `docker` (Python SDK), `coloredlogs`, `PyYAML` — see `requirements.txt`.
