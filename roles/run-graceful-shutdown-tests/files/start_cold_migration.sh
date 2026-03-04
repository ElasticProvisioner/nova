#!/bin/bash
source /opt/stack/devstack/openrc admin
set -x
set -e

timeout=196

server_cm=$1

image_id=$(openstack image list -f value -c ID | awk 'NR==1{print $1}')
flavor_id=$(openstack flavor list -f value -c ID | awk 'NR==1{print $1}')
network_id=$(openstack network list --no-share -f value -c ID | awk 'NR==1{print $1}')

echo "Creating test server on subnode for graceful shutdown cold migration test"
openstack --os-compute-api-version 2.74 server create --image ${image_id} --flavor ${flavor_id} \
--nic net-id=${network_id} --host ${SUBNODE_HOSTNAME} --wait ${server_cm}

echo "Starting cold migration of ${server_cm} to ${CONTROLLER_HOSTNAME}"
openstack --os-compute-api-version 2.56 server migrate \
    --host ${CONTROLLER_HOSTNAME} ${server_cm}

# Wait for the migrations to be in progress before returning so that the
# SIGTERM can be sent while the migrations are in progress.
count=0
while true; do
    cold_migration_status=$(openstack server migration list ${server_cm} -f value -c Status 2>/dev/null | head -1)
    server_task_state=$(openstack server show ${server_cm} -f value -c OS-EXT-STS:task_state 2>/dev/null)
    server_status=$(openstack server show ${server_cm} -f value -c status 2>/dev/null)
    if [ "${cold_migration_status}" == "migrating" ] || \
       [ "${cold_migration_status}" == "post-migrating" ] || \
       [ "${server_task_state}" == "resize_migrating" ] || \
       [ "${server_task_state}" == "resize_migrated" ] || \
       [ "${server_task_state}" == "resize_finish" ]; then
        echo "Cold migration is in progress"
        break
    elif [ "${cold_migration_status}" == "finished" ] || [ "${server_status}" == "VERIFY_RESIZE" ]; then
        echo "Cold migration appears to have already completed"
        exit 2
    fi

    count=$((count+1))
    if [ ${count} -eq ${timeout} ]; then
        echo "Timed out waiting for migrations to start"
        exit 2
    fi
done
