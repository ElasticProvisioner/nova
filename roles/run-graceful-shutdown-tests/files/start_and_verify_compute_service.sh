#!/bin/bash
set -x
set -e

COMPUTE_HOST=$1
EXPECTED_STATE=${2:-active}

get_service_status() {
  local host=$1
  local status
  status=$(ssh "${host}" systemctl is-active devstack@n-cpu || true)
  echo "${status}"
}

wait_for_service_state() {
  local host=$1
  local expected=$2
  local timeout=${3:-30}
  local count=0
  local status

  status=$(get_service_status "${host}")
  while [ "${status}" != "${expected}" ]; do
    sleep 5
    count=$((count+1))
    if [ ${count} -eq ${timeout} ]; then
      echo "Timed out waiting for compute service on ${host} to be ${expected} (current: ${status})"
      exit 5
    fi
    status=$(get_service_status "${host}")
  done
  echo "Compute service on ${host} is ${expected}"
}

if [ "${EXPECTED_STATE}" == "active" ] && [ "$(get_service_status "${COMPUTE_HOST}")" != "active" ]; then
    ssh "${COMPUTE_HOST}" sudo systemctl start devstack@n-cpu
fi

wait_for_service_state "${COMPUTE_HOST}" "${EXPECTED_STATE}"
