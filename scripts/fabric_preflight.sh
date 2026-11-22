#!/usr/bin/env bash
# Diagnostic ONLY. Does not change Docker configuration, containers or Fabric ledger.
set -u
echo '=== SmartTrace Fabric preflight (read-only) ==='
echo "WSL: ${WSL_DISTRO_NAME:-not detected}; working directory: $PWD"
echo '[1] Docker CLI'
if command -v docker >/dev/null 2>&1; then docker --version; else echo 'Docker CLI missing'; fi
echo '[2] Docker daemon connectivity'
if ! docker ps --format '{{.Names}} : {{.Status}}'; then
  echo 'ERROR: Docker engine unavailable. Fix Docker Desktop before network.sh.' >&2
  if command -v curl >/dev/null 2>&1 && [ -S /var/run/docker.sock ]; then
    echo 'Socket probe:'
    curl --max-time 5 --silent --show-error --output /dev/null --write-out 'HTTP %{http_code}\n' --unix-socket /var/run/docker.sock http://localhost/_ping || true
  fi
  exit 2
fi
echo '[3] Go and Fabric source checks'
if command -v go >/dev/null 2>&1; then go version; else echo 'Go missing'; fi
if [ -f blockchain/chaincode/main.go ] && [ -f blockchain/gateway/main.go ]; then
  echo 'Project Go sources: found in current project directory'
else
  echo 'Project Go sources: not in current directory. cd to your SmartTrace project root.'
fi
if [ -f "$HOME/fabric-samples/test-network/network.sh" ]; then echo 'Fabric test-network script: present'; else echo 'Fabric test-network script: missing'; fi
echo 'Preflight completed; no containers or data modified.'
