#! /bin/bash
# Initial sample workload for use with the testy framework.
set -e 

describe() {
    echo "A sample workload for use with the testy framework."
}

populate() {
    echo "Populate is not defined."
}

run() {
    export PYTHONPATH=${wt_build_dir}/bench/workgen:${wt_build_dir}/../bench/workgen/runner:${wt_build_dir}/lang/python:$PYTHONPATH
    ${script_dir}/testy-metrics.sh workload_status 1
    python3 ${workload_dir}/sample/sample_run.py --home ${database_dir} --keep
    ${script_dir}/testy-metrics.sh workload_status 0
}

validate() {
    set -o pipefail
    export PYTHONPATH=${wt_build_dir}/lang/python:${wt_home_dir}/tools:$PYTHONPATH
    validation_logs=${failure_dir}/${failure_file}
    database_path=$1/$database_dir
    echo "Database path: $database_path"
    echo "Logs saved to: $validation_logs"
    echo "Running verify..."
    free -h | sudo tee $validation_logs
    df -h | sudo tee -a $validation_logs
    du -h "$database_path" | sudo tee -a $validation_logs
    ${wt_build_dir}/wt -h "$database_path" -R verify 2>&1 | sudo tee -a $validation_logs
    echo "Validating mirrors..."
    python3 ${wt_home_dir}/bench/workgen/validate_mirror_tables.py "$database_path" 2>&1 | sudo tee -a $validation_logs
    sudo rm -f $validation_logs
}

"$@"
