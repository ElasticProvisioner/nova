#!/bin/bash
source /opt/stack/devstack/openrc admin
set -x
set -e

server=$1

# Wait for the server to finish cold migration and reach VERIFY_RESIZE state,
# which indicates the migration has completed and is awaiting confirmation.
timeout=360
count=0
migration_start=$(date +%s)
while true; do
    status=$(openstack server show ${server} -f value -c status)
    task_state=$(openstack server show ${server} -f value -c OS-EXT-STS:task_state)

    if [ "${status}" == "VERIFY_RESIZE" ] && { [ "${task_state}" == "None" ] || [ -z "${task_state}" ]; }; then
        migration_end=$(date +%s)
        migration_duration=$((migration_end - migration_start))
        echo "Cold migration completed in ${migration_duration} seconds."
        break
    fi

    if [ "${status}" == "ERROR" ]; then
        echo "Server went to ERROR status during cold migration"
        exit 6
    fi

    sleep 5
    count=$((count+1))
    if [ ${count} -eq ${timeout} ]; then
        echo "Timed out waiting for cold migration to complete"
        exit 5
    fi
done
