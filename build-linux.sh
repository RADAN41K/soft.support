#!/bin/bash
# Build SoftSupport binary + .deb for Ubuntu 22.04 via Docker
set -e

VERSION=$(cat VERSION | tr -d '[:space:]')

docker build --platform linux/amd64 -t soft-build .
docker run --platform linux/amd64 --name soft-build-run soft-build
mkdir -p dist
docker cp "soft-build-run:/app/dist/SoftSupport" ./dist/SoftSupport-linux
docker cp "soft-build-run:/app/dist/limansoft-support_${VERSION}_amd64.deb" ./dist/
docker rm soft-build-run
echo "Done:"
echo "  dist/SoftSupport-linux"
echo "  dist/limansoft-support_${VERSION}_amd64.deb"
