#! /bin/bash
# Initial sample workload for use with the Testy framework.

backup() {
    # Trigger the backup.
    sudo ${wt_build_dir}/wt -h ${database_dir} backup "$1"

    if test "$?" -ne "0"; then
        echo "FAILED"
    fi
}

describe() {
    echo "A sample workload for use with the testy framework."
}

populate() {
    export PYTHONPATH=${wt_build_dir}/bench/workgen:${wt_build_dir}/lang/python:$PYTHONPATH
    python3 ${workload_dir}/sample/sample_populate.py --home ${database_dir} --keep
}

run() {
    export PYTHONPATH=${wt_build_dir}/bench/workgen:${wt_build_dir}/lang/python:$PYTHONPATH
    python3 ${workload_dir}/sample/sample_run.py --home ${database_dir} --keep
}

validate() {
    echo "validate(): Not yet implemented."
}

"$@"
