"""
Root-level conftest.py for pytest.

Patches sys.argv and docker.DockerClient early so that module-level
initialization in config.py and main.py does not fail during test
collection (parse_args reading pytest args, DockerClient connecting
to a real Docker socket).
"""

import sys
from unittest.mock import MagicMock

# config.py calls parse_args() at module level, which reads sys.argv.
# When running under pytest, sys.argv contains pytest args that config.py
# does not recognize, causing a sys.exit(1). We sanitize sys.argv here
# so the initial module import succeeds cleanly.
_original_argv = sys.argv
sys.argv = [sys.argv[0]]

# main.py calls create_docker_client(config) at module level (line 43),
# which instantiates docker.DockerClient and connects to the Docker socket.
# We patch DockerClient before main.py is imported so no real connection
# is attempted during test collection.
import docker  # noqa: E402

docker.DockerClient = MagicMock
