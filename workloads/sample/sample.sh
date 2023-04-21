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
    export PYTHONPATH=${wt_build_dir}/bench/workgen:${wt_build_dir}/../bench/workgen/runner:${wt_build_dir}/lang/python:$PYTHONPATH
    python3 ${workload_dir}/sample/sample_run.py --home ${database_dir} --keep
}

validate() {
    export PYTHONPATH=${wt_build_dir}/lang/python:${wt_home_dir}/tools:$PYTHONPATH
    # Run recovery as part of validation.
    # The script still needs an action to perform after recovery, use 'list' to make it happy.
    ${wt_build_dir}/wt -h "$1/$database_dir" -R list
    python3 ${wt_home_dir}/bench/workgen/validate_mirror_tables.py "$1/$database_dir"
}

"$@"
