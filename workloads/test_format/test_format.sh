#! /bin/bash
# Initial sample workload for use with the testy framework.

describe() {
    echo "A test/format workload for use with the testy framework."
}

populate() {
    echo "Populate is not implemented in this wokrload."
}

run() {
    ${script_dir}/testy-metrics.sh workload_status 1
    # Test format will stop on first failure. 
    ${wt_build_dir}/test/format/format.sh -F -c ${workload_dir}/test_format/${config_file} -h ${database_dir} -j $(nproc)
    echo "Test format exited, please check for failure."
    ${script_dir}/testy-metrics.sh workload_status 0
}

validate() {
    echo "Validate is not implemented in this wokrload."
}

"$@"
