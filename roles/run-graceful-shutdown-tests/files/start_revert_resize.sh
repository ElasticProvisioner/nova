#!/bin/bash
source /opt/stack/devstack/openrc admin
set -x
set -e

timeout=196

image_id=$(openstack image list -f value -c ID | awk 'NR==1{print $1}')
flavor_id=$(openstack flavor list -f value -c ID | awk 'NR==1{print $1}')
network_id=$(openstack network list --no-share -f value -c ID | awk 'NR==1{print $1}')

echo "Creating test server on subnode for graceful shutdown revert resize test"
openstack --os-compute-api-version 2.74 server create --image ${image_id} --flavor ${flavor_id} \
    --nic net-id=${network_id} --host ${SUBNODE_HOSTNAME} --wait server-rr

echo "Migrate server-rr to ${CONTROLLER_HOSTNAME}"
openstack --os-compute-api-version 2.56 server migrate \
    --host ${CONTROLLER_HOSTNAME} server-rr

# Wait for the migrate to complete
count=0
while true; do
    status=$(openstack server show server-rr -f value -c status)
    if [ "${status}" == "VERIFY_RESIZE" ]; then
        echo "Migration completed, server is in VERIFY_RESIZE state"
        break
    fi
    if [ "${status}" == "ERROR" ]; then
        echo "Server went to ERROR status during cold migration"
        exit 2
    fi
    sleep 5
    count=$((count+1))
    if [ ${count} -eq 20 ]; then
        echo "Timed out waiting for server-rr to reach VERIFY_RESIZE"
        exit 2
    fi
done

# Start and wait for the revert resize to be in progress.
count=0
revert_started=False
revert_completed=False

status=$(openstack server show server-rr -f value -c status)
if [ "${status}" == "VERIFY_RESIZE" ]; then
    echo "Starting revert resize of server-rr"
    openstack server resize revert server-rr
else
    echo "Revert resize skipped"
    exit 2
fi

while true; do
    task_state=$(openstack server show server-rr -f value -c OS-EXT-STS:task_state)
    status=$(openstack server show server-rr -f value -c status)

    if [ "${revert_started}" != "True" ] && [ "${revert_completed}" != "True" ]; then
        if [ "${task_state}" == "resize_reverting" ]; then
            echo "Revert resize is in progress"
        # task_state is set by the API before it send the revert_resize RPC call
        # to compute. We can try to sleep here for 2 sec and see if compute start
        # the revert_resize and shutdown can be initiated before it finish. This
        # is best try but no guarantee for that timing.
            sleep 2
            revert_started=True
        fi
        if [ "${status}" == "ACTIVE" ]; then
            echo "Revert resize appears to have already completed"
            revert_completed=True
        fi
    fi

    if [ "${revert_started}" == "True" ]; then
        break
    fi

    if [ "${revert_completed}" == "True" ]; then
        echo "Revert resize completed before SIGTERM was sent"
        exit 2
    fi

    count=$((count+1))
    if [ ${count} -eq ${timeout} ]; then
        echo "Timed out waiting for revert resize to start"
        exit 2
    fi
done
