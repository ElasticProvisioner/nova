#!/bin/bash
source /opt/stack/devstack/openrc admin
set -x
set -e

confirm_resize() {
    local server=$1

    echo "Confirming resize on ${server}"
    openstack server resize confirm "${server}"

    count=0
    while true; do
        status=$(openstack server show "${server}" -f value -c status 2>/dev/null || echo "NOT_FOUND")
        if [ "${status}" == "ACTIVE" ] || [ "${status}" == "ERROR" ]; then
            break
        fi
        sleep 5
        count=$((count+1))
        if [ ${count} -eq 10 ]; then
            echo "Timed out waiting for ${server} to be ACTIVE or Error after confirm resize"
            break
        fi
    done
}

cleanup_server() {
    local server=$1

    status=$(openstack server show "${server}" -f value -c status 2>/dev/null || echo "NOT_FOUND")

    if [ "${status}" == "VERIFY_RESIZE" ]; then
        confirm_resize "${server}"
    fi

    status=$(openstack server show "${server}" -f value -c status 2>/dev/null || echo "NOT_FOUND")
    if [ "${status}" == "ACTIVE" ] || [ "${status}" == "ERROR" ]; then
        echo "Deleting ${server} (status: ${status})"
        openstack server delete --wait "${server}"
    else
        echo "Skipping ${server} deletion (status: ${status})"
    fi
}

for server in "$@"; do
    cleanup_server "${server}"
done
