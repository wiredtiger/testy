#!/bin/bash

main() {
    # Exit if the backup service is active.
    local _workload=$1
    if systemctl is-active --quiet testy-backup@"$_workload".service; then
        echo "The backup service is currently running."
        exit 1
    fi

    # Kill all Python3 processes.
    sudo killall -SIGKILL python3
}

# Run main function.
main "$@"
