#!/usr/bin/env bash
# Service UID/GID reservation; no host login accounts are created for these IDs.
check_service_identities() {
  local service_id
  for service_id in 20001 20002 20003; do
    if getent passwd "$service_id" >/dev/null; then
      echo "Reserved service UID $service_id is occupied by a host account" >&2
      return 1
    fi
    if getent group "$service_id" >/dev/null; then
      echo "Reserved service GID $service_id is occupied by a host group" >&2
      return 1
    fi
  done
}
