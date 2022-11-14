#! /bin/bash
# A template for defining testy workloads. 

describe() {
    :
}

populate() {
    python3 sample_populate.py
}

run() {
    :
}

validate() {
    :
}

"$@"
