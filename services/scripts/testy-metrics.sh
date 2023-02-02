#!/bin/bash

# The script expects in order: the name, namespace and value of the metric.
# All of them should be of type string.
_metric_name=$1
_metric_namespace=$2
_metric_value=$3

_aws_endpoint="http://169.254.169.254/latest/meta-data/"
_instance_id=$(curl ${_aws_endpoint}/instance-id 2> /dev/null)

if ! aws cloudwatch put-metric-data --metric-name "$_metric_name" --dimensions Instance="$_instance_id" --namespace "$_metric_namespace" --value "$_metric_value"; then
    echo "Error: Failed calling put-metric-data (instanceID: $_instance_id, name: $_metric_name, namespace: $_metric_namespace, value:$_metric_value)."
    exit 1
fi
