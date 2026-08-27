#!/bin/bash
#
# Generate Docker tags from a SemVer Git tag.
#
# This script takes a Git tag in the format "vX.Y.Z" and generates a list
# of Docker tags that should be applied to the image. The output is a
# comma-separated list of tags suitable for docker/build-push-action's
# `tags` input.
#
# Usage:
#   ./scripts/generate-tags.sh <git_tag> <docker_repo> [<docker_repo_2> ...]
#
# Example:
#   ./scripts/generate-tags.sh v1.2.3 ghcr.io/obeone/app docker.io/obeoneorg/app
#   Output:
#     ghcr.io/obeone/app:v1.2.3,ghcr.io/obeone/app:v1.2,ghcr.io/obeone/app:v1,\\
#     ghcr.io/obeone/app:1.2.3,ghcr.io/obeone/app:1.2,ghcr.io/obeone/app:1,\\
#     docker.io/obeoneorg/app:v1.2.3,...

set -euo pipefail

# --- Main execution ---

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <git_tag> <docker_repo> [<docker_repo_2> ...]" >&2
    exit 1
fi

GIT_TAG="$1"
shift
REPOS=("$@")

# Remove the 'v' prefix to get the plain version number.
PLAIN_VERSION=${GIT_TAG#v}

# Split the version into major, minor, and patch components.
MAJOR=$(echo "$PLAIN_VERSION" | cut -d. -f1)
MINOR=$(echo "$PLAIN_VERSION" | cut -d. -f2)
PATCH=$(echo "$PLAIN_VERSION" | cut -d. -f3)

# Check if all version components are present.
if [ -z "$MAJOR" ] || [ -z "$MINOR" ] || [ -z "$PATCH" ]; then
    echo "Error: Invalid tag format. Expected vX.Y.Z, but got $GIT_TAG" >&2
    exit 1
fi

TAGS=()

for repo in "${REPOS[@]}"; do
    TAGS+=(
        "${repo}:${GIT_TAG}"
        "${repo}:v${MAJOR}.${MINOR}"
        "${repo}:v${MAJOR}"
        "${repo}:${PLAIN_VERSION}"
        "${repo}:${MAJOR}.${MINOR}"
        "${repo}:${MAJOR}"
    )
done

# Join with commas for docker/build-push-action `tags` input
IFS=','
printf '%s' "${TAGS[*]}"
