#!/bin/bash

# The script expects in order: the name and the value of the metric.
_metric_name=$1
_metric_value=$2
_metric_namespace=testy

_aws_endpoint="http://169.254.169.254/latest/meta-data/"
_instance_id=$(curl ${_aws_endpoint}/instance-id 2> /dev/null)

if ! aws cloudwatch put-metric-data --metric-name "$_metric_name" --dimensions Instance="$_instance_id" --namespace "$_metric_namespace" --value "$_metric_value"; then
    echo "Error: Failed calling put-metric-data (instance: $_instance_id, metric name: $_metric_name, metric value: $_metric_value, metric namespace: $_metric_namespace)."
    exit 1
fi
