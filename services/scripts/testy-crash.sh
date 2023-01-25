#!/bin/bash

main() {
    # Exit if the backup service is active.
    local _workload=$1
    if systemctl is-active --quiet testy-backup@"$_workload".service; then
        echo "The backup service is currently running."
        exit 1
    fi

    # Retrieve the Python process and send a SIGKILL.
    if ! pgrep -U testy python &> /dev/null; then
        echo "Failed to find running Python process."
        exit 1
    fi
    local _python_pid
    _python_pid=$(pgrep -U testy python)

    if ! sudo kill -SIGKILL "$_python_pid"; then
        echo "Failed to kill Python process $_python_pid"
        exit 1
    fi
}

# Run main function.
main "$@"
