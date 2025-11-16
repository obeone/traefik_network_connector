#!/bin/bash
#
# bump-version.sh
#
# This script bumps the version in the VERSION file according to SemVer.
# It takes one argument: patch, minor, or major.
# It also handles git commit and tag creation.
#

set -euo pipefail

# --- Functions ---

# Function to display help message
usage() {
  cat <<EOF
Usage: $(basename "$0") [patch|minor|major]
Bumps the version in the VERSION file.

Arguments:
  patch   Increment the patch version (e.g., 0.1.0 -> 0.1.1)
  minor   Increment the minor version (e.g., 0.1.0 -> 0.2.0)
  major   Increment the major version (e.g., 0.1.0 -> 1.0.0)

Options:
  --help  Display this help message and exit
EOF
}

# --- Main script ---

# Check for --help argument
if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

# Check for correct number of arguments
if [ "$#" -ne 1 ]; then
  usage
  exit 1
fi

# Check for valid argument
BUMP_TYPE=$1
if [[ "$BUMP_TYPE" != "patch" && "$BUMP_TYPE" != "minor" && "$BUMP_TYPE" != "major" ]]; then
  usage
  exit 1
fi

# Read the current version from the VERSION file
VERSION_FILE="VERSION"
if [ ! -f "$VERSION_FILE" ]; then
  echo "Error: VERSION file not found!"
  exit 1
fi
CURRENT_VERSION=$(cat "$VERSION_FILE")

# Split the version into major, minor, and patch parts
IFS='.' read -r -a VERSION_PARTS <<< "$CURRENT_VERSION"
MAJOR=${VERSION_PARTS[0]}
MINOR=${VERSION_PARTS[1]}
PATCH=${VERSION_PARTS[2]}

# Increment the correct part of the version
case "$BUMP_TYPE" in
  major)
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
    ;;
  minor)
    MINOR=$((MINOR + 1))
    PATCH=0
    ;;
  patch)
    PATCH=$((PATCH + 1))
    ;;
esac

# Assemble the new version
NEW_VERSION="$MAJOR.$MINOR.$PATCH"

# Write the new version to the VERSION file
echo "$NEW_VERSION" > "$VERSION_FILE"

# Print the new version to stdout
echo "$NEW_VERSION"

# Commit the new version and create a git tag
git add "$VERSION_FILE"
git commit -m "Bump version to $NEW_VERSION"
git tag "v$NEW_VERSION"