#!/bin/sh
REPO="$(cd "$(dirname "$0")/..";pwd)"
protoc --python_out="$REPO/src/gtfs_binary" -I"$REPO/protobuf" "$REPO/protobuf"/*.proto
