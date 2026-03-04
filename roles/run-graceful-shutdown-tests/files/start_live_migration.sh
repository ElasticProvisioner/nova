#!/bin/bash
source /opt/stack/devstack/openrc admin
set -x
set -e

timeout=196

server_lm=$1

image_id=$(openstack image list -f value -c ID | awk 'NR==1{print $1}')
flavor_id=$(openstack flavor list -f value -c ID | awk 'NR==1{print $1}')
network_id=$(openstack network list --no-share -f value -c ID | awk 'NR==1{print $1}')

echo "Creating test server on subnode for graceful shutdown live migration test"
openstack --os-compute-api-version 2.74 server create --image ${image_id} --flavor ${flavor_id} \
--nic net-id=${network_id} --host ${SUBNODE_HOSTNAME} --wait ${server_lm}

echo "Starting live migration of ${server_lm} to ${CONTROLLER_HOSTNAME}"
openstack server migrate --live-migration \
--host ${CONTROLLER_HOSTNAME} ${server_lm}

# Wait for the migration to be in progress before returning so that the
# SIGTERM can be sent while the migrations are in progress.
count=0
while true; do
    migration_status=$(openstack server migration list ${server_lm} \
        -f value -c Status 2>/dev/null | head -1)
    server_status=$(openstack server show ${server_lm} \
        -f value -c status 2>/dev/null)
    task_state=$(openstack server show ${server_lm} \
        -f value -c OS-EXT-STS:task_state 2>/dev/null)
    if [ "${migration_status}" == "preparing" ] || \
       [ "${migration_status}" == "running" ] || \
       [ "${task_state}" == "migrating" ]; then
        echo "Live migration is in progress (status: ${migration_status}, task_state: ${task_state})"
        break
    elif [ "${migration_status}" == "completed" ] || \
         { [ "${server_status}" == "ACTIVE" ] && \
           { [ "${task_state}" == "None" ] || [ -z "${task_state}" ]; }; }; then
        echo "Live migration has already completed"
        exit 2
    fi

    count=$((count+1))
    if [ ${count} -eq ${timeout} ]; then
        echo "Timed out waiting for migrations to start"
        exit 2
    fi
done
