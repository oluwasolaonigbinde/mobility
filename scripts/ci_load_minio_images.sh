#!/usr/bin/env bash
# Load the MinIO server and client images CI has pinned since Package 8.
#
# quay.io/minio/minio@sha256:d249d1fb6966de4d8ad26c04754b545205ff15a62e4fd19ebd0f26fa5baacbc0 and
# quay.io/minio/mc@sha256:fb8f773eac8ef9d6da0486d5dec2f42f219358bcb8de579d1623d518c9ebd4cc
# are no longer publicly pullable (Sep 2026). Unmodified `docker save` exports
# of those exact images are attached to this repository's
# `ci-images-minio-2025-07` release; the checksums below pin them.
set -euo pipefail

base="https://github.com/oluwasolaonigbinde/mobility/releases/download/ci-images-minio-2025-07"
minio="minio-RELEASE.2025-07-23T15-54-02Z.tar.gz"
mc="mc-RELEASE.2025-07-21T05-28-08Z.tar.gz"
dir="$(mktemp -d)"
trap 'rm -rf "$dir"' EXIT

for file in "$minio" "$mc"; do
  curl -fsSL --retry 3 -o "$dir/$file" "$base/$file"
done
(
  cd "$dir"
  sha256sum -c - <<EOF
8367872214ecc1ca919b7b7e3a28e4e13cfd9b6ca7609b4028dbfa4be03d7610  $minio
ef6be78bd425b192300ad2acc614a9e3d61f805d3d07b0fddc52a64789ecec1a  $mc
EOF
)
for file in "$minio" "$mc"; do
  gunzip -c "$dir/$file" | docker load
done
docker image inspect \
  minio/minio:RELEASE.2025-07-23T15-54-02Z \
  minio/mc:RELEASE.2025-07-21T05-28-08Z >/dev/null
