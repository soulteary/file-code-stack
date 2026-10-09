#!/usr/bin/env bash
# Build the operator tools on the management computer, never in the server data tree.
set -euo pipefail
release=RELEASE.2026-10-09T14-38-15Z
source_sha=c62be561ef03f9b7749c53a2e71b3886efa76db4
[[ $# -eq 1 && ! -e $1 ]] || { echo 'Usage: build-oc.sh NEW_OUTPUT_DIRECTORY' >&2; exit 1; }
output=$1
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git clone --quiet --depth 1 --branch "$release" https://github.com/soulteary/oc.git "$work/source"
[[ $(git -C "$work/source" rev-parse HEAD) == "$source_sha" ]] || { echo 'OC source identity mismatch' >&2; exit 1; }
mkdir "$work/tools"
(
  cd "$work/source"
  export GOWORK=off GOTOOLCHAIN=local CGO_ENABLED=0
  ldflags="-s -w -X github.com/soulteary/mc/cmd.Version=2026-10-09T14:38:15Z -X github.com/soulteary/mc/cmd.ReleaseTag=$release -X github.com/soulteary/mc/cmd.CommitID=$source_sha -X github.com/soulteary/mc/cmd.ShortCommitID=${source_sha:0:12}"
  go build -mod=readonly -trimpath -ldflags "$ldflags" -o "$work/tools/oc" .
  go build -mod=readonly -trimpath -ldflags "-X main.version=$release" -o "$work/tools/oc-console" ./cmd/oc-console
)
printf '%s\n%s\n' "$release" "$source_sha" > "$work/tools/SOURCE"
# Refuse an existing destination, including one created during the build.
mkdir "$output"
cp "$work/tools/oc" "$work/tools/oc-console" "$work/tools/SOURCE" "$output/"
echo "Built OC and oc-console $release in $output"
