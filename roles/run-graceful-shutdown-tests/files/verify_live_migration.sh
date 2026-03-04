#!/bin/bash
source /opt/stack/devstack/openrc admin
set -x
set -e

server=$1

# Wait for the server to finish live migration and become ACTIVE with
# no task_state, which indicates the migration has completed.
timeout=360
count=0
migration_start=$(date +%s)
while true; do
    status=$(openstack server show ${server} -f value -c status)
    task_state=$(openstack server show ${server} -f value -c OS-EXT-STS:task_state)

    if [ "${status}" == "ACTIVE" ] && { [ "${task_state}" == "None" ] || [ -z "${task_state}" ]; }; then
        migration_end=$(date +%s)
        migration_duration=$((migration_end - migration_start))
        echo "Migration is completed in ${migration_duration} seconds."
        break
    fi

    if [ "${status}" == "ERROR" ]; then
        echo "Server went to ERROR status during live migration"
        exit 3
    fi

    sleep 5
    count=$((count+1))
    if [ ${count} -eq ${timeout} ]; then
        echo "Timed out waiting for live migration to complete"
        exit 5
    fi
done

# Make sure the server moved to the controller.
host=$(openstack server show ${server} -f value -c OS-EXT-SRV-ATTR:host)
if [[ ${host} != ${CONTROLLER_HOSTNAME} ]]; then
    echo "Unexpected host ${host} for server after live migration during graceful shutdown."
    exit 4
fi

echo "Live migration during graceful shutdown completed successfully"
echo "Server ${server} is ACTIVE on ${host}"
