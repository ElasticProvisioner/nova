#!/bin/bash
source /opt/stack/devstack/openrc admin
set -x
set -e

# Wait for the server to finish building and become active which confirms that
# the build completed during graceful shutdown.
build_start=$(date +%s)
while true; do
    status=$(openstack server show server-build -f value -c status)

    if [ "${status}" == "ACTIVE" ]; then
        build_end=$(date +%s)
        build_duration=$((build_end - build_start))
        echo "Build completed in ${build_duration} seconds."
        break
    fi

    if [ "${status}" == "ERROR" ]; then
        echo "Server went to ERROR status."
        exit 6
    fi

    sleep 5
done
