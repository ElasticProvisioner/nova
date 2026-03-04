#!/bin/bash
source /opt/stack/devstack/openrc admin
set -x
set -e

# Wait for the server to finish reverting resize
revert_start=$(date +%s)
while true; do
    status=$(openstack server show server-rr -f value -c status)
    task_state=$(openstack server show server-rr -f value -c OS-EXT-STS:task_state)

    if [ "${status}" == "ACTIVE" ] && { [ "${task_state}" == "None" ] || [ -z "${task_state}" ]; }; then
        revert_end=$(date +%s)
        revert_duration=$((revert_end - revert_start))
        echo "Revert resize completed in ${revert_duration} seconds."
        break
    fi

    if [ "${status}" == "ERROR" ]; then
        echo "Server went to ERROR status during revert resize"
        exit 3
    fi

    sleep 5
done

# Make sure the server moved back to the subnode.
host=$(openstack server show server-rr -f value -c OS-EXT-SRV-ATTR:host)
if [ "${host}" != "${SUBNODE_HOSTNAME}" ]; then
    echo "Unexpected host ${host} for server after revert resize during graceful shutdown."
    exit 4
fi

echo "Revert resize during graceful shutdown completed successfully"
echo "Server server-rr is ACTIVE on ${host}"
