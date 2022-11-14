#! /bin/bash
# Initial sample workload for use with the Testy framework.

describe() {
    :
}

populate() {
    export PYTHONPATH=${wt_build_dir}/bench/workgen:${wt_build_dir}/lang/python:$PYTHONPATH
    python3 ${workload_dir}/sample/sample_populate.py
}

run() {
    :
}

validate() {
    :
}

"$@"
