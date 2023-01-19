#!/bin/bash
# Instance ID where testy runs.
# testy_instance_id=i-0592a17964c056392
testy_instance_id=$(aws ec2 describe-instances --filters "Name=key-name,Values=etienne-rsa" --query "Reservations[*].Instances[*].InstanceId" --output text)
echo "Testy instance ID: $testy_instance_id"

# Retrieve the volume ID used on this instance.
testy_volume_id=$(aws ec2 describe-volumes --filters Name=attachment.instance-id,Values="$testy_instance_id" --query "Volumes[*].{ID:VolumeId}" --output text)
if [ -z "$testy_volume_id" ]; then
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
    echo "Volume ID from Testy instance not found."
    exit 1
fi
echo "Testy volume ID: $testy_volume_id"

# Create a snapshot of the instance.
echo -e "\nTaking a snapshot of the volume $testy_volume_id..."
snapshot=$(aws ec2 create-snapshot --volume-id "$testy_volume_id" --description "New snapshot")
if [ $? != 0 ]; then
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name backup --dimensions Instance="$testy_instance_id" --namespace "backup" --value -1)
    exit 1
fi

cloudwatch=$(aws cloudwatch put-metric-data --metric-name backup --dimensions Instance="$testy_instance_id" --namespace "backup" --value 1)

# Either parse the output or use retrieve the latest snapshot.
snapshot_id=$(less "$snapshot" | jq -r .SnapshotId)
#snapshot_id=$(aws ec2 describe-snapshots --filters Name=status,Values=completed --owner-ids self --query 'sort_by(Snapshots, &StartTime)[-1].SnapshotId' --output text)
echo "Testy snapshot ID: $snapshot_id"

# We need to wait for the snapshot to be ready for use.
echo -e "\nWaiting for the snapshot $snapshot_id to be completed..."
snapshot_status=$(aws ec2 describe-snapshots --snapshot-ids "$snapshot_id" --query "Snapshots[*].[State]" --output text)
until [ "$snapshot_status" == "completed" ]
do
   echo "snapshot_status: $snapshot_status"
   sleep 10
   snapshot_status=$(aws ec2 describe-snapshots --snapshot-ids "$snapshot_id" --query "Snapshots[*].[State]" --output text)
done
echo "snapshot_status: $snapshot_status"

# Create a volume using the snapshot.
echo -e "\nCreating a volume from the snapshot $snapshot_id..."
volume=$(aws ec2 create-volume --snapshot-id "$snapshot_id" --availability-zone ap-southeast-2c)
if [ $? != 0 ]; then
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
    exit 1
fi
volume_id=$(less "$volume" | jq -r .VolumeId)
echo "Snapshot volume ID: $volume_id"

# We need to wait for the volume to be ready for use.
echo -e "\nWaiting for the volume $volume_id to be ok..."
volume_status=$(aws ec2 describe-volume-status --volume-ids "$volume_id" --query "VolumeStatuses[*].VolumeStatus.Status" --output text)
until [ "$volume_status" == "ok" ]
do
   echo "volume_status: $volume_status"
   sleep 10
volume_status=$(aws ec2 describe-volume-status --volume-ids "$volume_id" --query "VolumeStatuses[*].VolumeStatus.Status" --output text)
done
echo "volume_status: $volume_status"
# Check the volume is available.
echo -e "\nWaiting for the volume $volume_id to be available..."
volume_state=$(aws ec2 describe-volumes --volume-ids "$volume_id" --query "Volumes[*].State" --output text)
until [ "$volume_state" == "available" ]
do
    echo "volume_state: $volume_state"
    sleep 10
    volume_state=$(aws ec2 describe-volumes --volume-ids "$volume_id" --query "Volumes[*].State" --output text)
done
echo "volume_state: $volume_state"

# Attach the volume to the instance.
# What if something is already attached here? We could check if there is another volume attached.
# Either wait, or attach to a different mounting point.
# Send an alert if that's the case. And exit here. 
echo -e "\nAttaching the volume $volume_id to the instance $testy_instance_id..."
attach=$(aws ec2 attach-volume --device xvdf --instance-id "$testy_instance_id" --volume-id "$volume_id")
if [ $? != 0 ]; then
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
    exit 1
fi

# Connect to the instance and mount the volume.
sleep 10
# TODO /mnt/<backup_folder>
# If something is already mounted, error.
echo -e "\nCreating the /backup_2..."
# TODO - Dont need to ssh, I am already on the machine.
ssh ubuntu@ec2-3-27-6-35.ap-southeast-2.compute.amazonaws.com 'sudo mkdir /backup_2'
# TODO Check the output of this command, if it exists, something is up.
echo "Mounting /dev/xvdf1 to /backup_2..."
ssh ubuntu@ec2-3-27-6-35.ap-southeast-2.compute.amazonaws.com 'sudo mount /dev/xvdf1 /backup_2'

# Verify a table.
echo -e "\nValidating database..."
validation=0
# ssh ubuntu@ec2-3-27-6-35.ap-southeast-2.compute.amazonaws.com 'cd /backup_2/srv/testy/data && sudo ../wiredtiger/build/wt -r verify -d dump_pages "file:table_14VmX.wt"'
ssh ubuntu@ec2-3-27-6-35.ap-southeast-2.compute.amazonaws.com '/backup_2/srv/testy/workloads/sample/sample.sh validate'
if [ $? != 0 ]; then
    validation=-1
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name validation --dimensions Instance="$testy_instance_id" --namespace "validation" --value "$validation")
    echo "!!VALIDATION FAILED!!"
    # Do not exit,
    # exit 1
else
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name validation --dimensions Instance="$testy_instance_id" --namespace "validation" --value 1)
fi

# When the validation is done, we can unmount and detach the volume.
echo -e "\nUnmounting /dev/xvdf1..."
ssh ubuntu@ec2-3-27-6-35.ap-southeast-2.compute.amazonaws.com 'sudo umount /dev/xvdf1'
echo "Detaching $volume_id..."
detach_volume=$(aws ec2 detach-volume --volume-id "$volume_id" --query "State" --output text)
if [ $? != 0 ]; then
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
    echo "Could not detach volume"
    exit 1
fi

# Delete the snapshot and the volume if the validation worked.
# TODO: Add tags to snapshots depending on the validation results.
if [ $validation == 0 ]; then

    echo "Deleting snapshot $snapshot_id..."
    delete_snapshot=$(aws ec2 delete-snapshot --snapshot-id "$snapshot_id")
    if [ $? != 0 ]; then
        cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
        echo "Could not delete snapshot $snapshot_id"
    fi

    # Check the volume is fully detached before deleting it.
    # TODO - Does the volume still exist after deleting the snapshots?
    # TODO - Call detach?
    # Should we keep the volume of the snapshot?
    echo "Waiting for the volume $volume_id to be available..."
    volume_state=$(aws ec2 describe-volumes --volume-ids "$volume_id" --query "Volumes[*].State" --output text)
    until [ "$volume_state" == "available" ]
    do
        echo "volume_state: $volume_state"
        sleep 10
        volume_state=$(aws ec2 describe-volumes --volume-ids "$volume_id" --query "Volumes[*].State" --output text)
    done
    echo "volume_state: $volume_state"

    echo "Deleting volume $volume_id..."
    delete_volume=$(aws ec2 delete-volume --volume-id "$volume_id")
    if [ $? != 0 ]; then
        cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
        echo "Could not delete volume $volume_id"
    fi
fi
exit

# # Retrieve the latest snapshot
# latest_snapshot_id=$(aws ec2 describe-snapshots --filters Name=status,Values=completed --owner-ids self --query 'sort_by(Snapshots, &StartTime)[-1].SnapshotId' --output text)
# if [ $? != 0 ]; then
#     return 1
# fi
# echo "Latest snapshot ID is $latest_snapshot_id"

# # Spawn a host with the snapshot id
# # AL2 ami ami-051a81c2bd3e755db
# # run_instances=$(aws ec2 run-instances --image-id ami-006fd15ab56f0fbe6 --instance-type t2.2xlarge --key-name etienne-rsa --security-group-ids sg-0aef800e555bfe4fc --block-device-mappings "[{\"DeviceName\":\"/dev/sdf\",\"Ebs\":{\"SnapshotId\":\"$latest_snapshot_id\"}}]")
# run_instances=$(aws ec2 run-instances --image-id ami-051a81c2bd3e755db --instance-type t2.micro --key-name etienne-rsa --security-group-ids sg-0aef800e555bfe4fc --block-device-mappings "[{\"DeviceName\":\"/dev/sdh\",\"Ebs\":{\"SnapshotId\":\"$latest_snapshot_id\"}}]")
# if [ $? != 0 ]; then
#     exit 1
# fi
# echo "$run_instances"

# # Retrieve the instance ID.
# instance_id=$(less $run_instances | jq '.Instances[0].InstanceId')
# if [ $? != 0 ]; then
#     exit 1
# fi
# echo "instance_id is $instance_id"

# # Check that the instance is up and running.
# describe_instance=$(aws ec2 describe-instance-status --instance-id $instance_id)
# if [ $? != 0 ]; then
#     exit 1
# fi
# status=$(less $describe_instance | jq '.InstanceStatuses[0].InstanceState.Name')
# if [ $? != 0 ]; then
#     exit 1
# fi
# echo "Status is $status"
