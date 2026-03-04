#!/bin/bash
source /opt/stack/devstack/openrc admin
set -x
set -e

timeout=60

image_id=$(openstack image list -f value -c ID | awk 'NR==1{print $1}')
flavor_id=$(openstack flavor list -f value -c ID | awk 'NR==1{print $1}')
network_id=$(openstack network list --no-share -f value -c ID | awk 'NR==1{print $1}')

echo "Creating test server on subnode"
openstack --os-compute-api-version 2.74 server create --image ${image_id} --flavor ${flavor_id} \
    --nic net-id=${network_id} --host ${SUBNODE_HOSTNAME} server-build

# Wait for the server vm_state to reach BUILDING so that we know that compute has
# started the build request.
count=0
while true; do
    vm_state=$(openstack server show server-build -f value -c OS-EXT-STS:vm_state)

    if [ "${vm_state}" == "building" ]; then
        echo "Server is in Building"
        break
    fi

    if [ "${vm_state}" == "active" ]; then
        echo "Server became active before SIGTERM was sent"
        exit 2
    fi

    if [ "${vm_state}" == "error" ]; then
        echo "Server went to error vm_state"
        exit 2
    fi

    sleep 1
    count=$((count+1))
    if [ ${count} -eq ${timeout} ]; then
        echo "Timed out waiting for server to reach BUILDING vm_state"
        exit 2
    fi
done
