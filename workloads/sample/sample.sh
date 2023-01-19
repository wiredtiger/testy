#! /bin/bash
# Initial sample workload for use with the testy framework.

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

backup() {
    ${workload_dir}/sample/sample_backup.sh
}

validate() {
    echo "validate(): Not yet implemented."
}

"$@"
