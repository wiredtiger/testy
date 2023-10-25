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
    ${wt_build_dir}/test/format/format.sh -c ${workload_dir}/test_format/${config_file} -h ${database_dir} -j $(nproc)
    ${script_dir}/testy-metrics.sh workload_status 0
}

validate() {
    echo "Running verify..."
    # Run verify in all the folders created by test/format.
    cd ${wt_build_dir}/test/format || exit
    for f in $(ls -d $1/$database_dir/*/);
    do
        ../../wt -h "$f" -R verify;
    done
    cd -
}

"$@"
