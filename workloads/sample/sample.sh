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
    ${script_dir}/testy-metrics.sh workload_status 1
    python3 ${workload_dir}/sample/sample_run.py --home ${database_dir} --keep
    ${script_dir}/testy-metrics.sh workload_status 0
}

validate() {
    export PYTHONPATH=${wt_build_dir}/lang/python:${wt_home_dir}/tools:$PYTHONPATH
    ${wt_build_dir}/wt -h "$1/$database_dir" -R verify
    python3 ${wt_home_dir}/bench/workgen/validate_mirror_tables.py "$1/$database_dir"
}

"$@"
