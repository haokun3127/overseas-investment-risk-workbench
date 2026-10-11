#!/usr/bin/env bash
# First installation only. Never replaces an existing Compose project or data.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
deployment_project=risk-workbench-isolated
deployment_port="${WORKBENCH_PORT:-18000}"
if [[ ! "$deployment_port" =~ ^[0-9]{1,5}$ ]] || ((10#$deployment_port < 1024 || 10#$deployment_port > 65535)); then
  echo 'Choose an unprivileged WORKBENCH_PORT between 1024 and 65535.' >&2
  exit 1
fi
if [[ "$(uname -s)" != Linux ]] || ! command -v docker >/dev/null || ! command -v ss >/dev/null; then
  echo 'Requires Linux, Docker Engine, Compose v2 and ss. No system packages were changed.' >&2
  exit 1
fi
docker_local() {
  env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock "$@"
}
docker_local info --format '{{.ServerVersion}}'
docker_local compose version
for resource in container volume network; do
  existing=()
  if [[ "$resource" == container ]]; then existing=(--all); fi
  if [[ -n "$(docker_local "$resource" ls "${existing[@]}" -q --filter "label=com.docker.compose.project=$deployment_project")" ]]; then
    echo 'An existing isolated deployment was found. Refusing to overwrite or reuse it; inspect it first.' >&2
    exit 1
  fi
done
if [[ -n "$(ss -H -ltn "sport = :$deployment_port")" ]]; then
  echo "Port $deployment_port is occupied. Choose another WORKBENCH_PORT." >&2
  exit 1
fi
if [[ "${1:-}" == --check ]]; then
  echo 'Preflight passed. No application files, containers or data were changed.'
  exit 0
fi
if [[ $# != 0 ]]; then
  echo 'Usage: bash scripts/deploy_isolated.sh [--check]' >&2
  exit 1
fi
deployment_env="${WORKBENCH_ENV_FILE:-.env}"
if [[ ! -e "$deployment_env" && ! -L "$deployment_env" ]]; then
  (set -o noclobber; cat .env.example >"$deployment_env")
  chmod 600 "$deployment_env"
fi
export WORKBENCH_PORT="$deployment_port" WORKBENCH_ENV_FILE="$deployment_env"
compose() { docker_local compose -f compose.server.yaml "$@"; }
compose config --quiet
if [[ -n "${WORKBENCH_BUILD_CA:-}" ]]; then
  docker_local build --secret "id=proxy_ca,src=$WORKBENCH_BUILD_CA" \
    -t "risk-workbench-isolated:${WORKBENCH_IMAGE_TAG:-local}" .
else
  compose build
fi
echo 'Initialize the administrator below. Password entry stays in this terminal.'
compose run --rm --no-deps workbench python -m scripts.manage init-admin
compose up -d --no-build --wait
echo "Workbench started on server loopback port $deployment_port. Use SSH forwarding or an HTTPS reverse proxy to access it."
