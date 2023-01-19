#!/bin/bash

# SSH Keys used by the testy user.
ssh_key_name=etienne-rsa
# Virtual block device.
virtual_device=/dev/xvdf1
# Where the backup is mounted.
backup_folder=/mnt/backup

# Retrieve the testy instance id using the ssh key.
testy_instance_id=$(aws ec2 describe-instances --filters "Name=key-name,Values=$ssh_key_name" --query "Reservations[*].Instances[*].InstanceId" --output text)
echo "Testy instance ID: $testy_instance_id"

# Retrieve the volume ID named as "root" on this instance.
testy_volume_id=$(aws ec2 describe-volumes --filters Name=attachment.instance-id,Values="$testy_instance_id" Name=tag:Name,Values="root" --query "Volumes[*].{ID:VolumeId}" --output text)
if [ -z "$testy_volume_id" ]; then
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
    echo "Volume ID from Testy instance not found."
    exit 1
fi
echo "Testy volume ID: $testy_volume_id"

# Create a snapshot of the instance with a tag indicating it should be processed.
echo -e "\nTaking a snapshot of the volume $testy_volume_id..."
snapshot=$(aws ec2 create-snapshot --volume-id "$testy_volume_id" --tag-specifications 'ResourceType=snapshot,Tags=[{Key=analysis,Value=pending}]' --description "Testy snapshot")
if [ $? != 0 ]; then
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name backup --dimensions Instance="$testy_instance_id" --namespace "backup" --value -1)
    exit 1
fi
snapshot_id=$(less "$snapshot" | jq -r .SnapshotId)
echo "Testy snapshot ID: $snapshot_id"

cloudwatch=$(aws cloudwatch put-metric-data --metric-name backup --dimensions Instance="$testy_instance_id" --namespace "backup" --value 1)

# Check if the virtual device is present. If it is, it can mean a backup is in progress or a volume has not been detached.
if ls $virtual_device > /dev/null; then
    echo "A backup is already in progress!"
    exit 1
fi

# TODO - We might be behind, retrieving snapshots that have not been treated should be done.
# snapshots=$(aws ec2 describe-snapshots --filters Name=status,Values=completed Name=volume-id,Values="$testy_volume_id" Name=tag:analysis,Values="pending" --owner-ids self)
# Latest snapshot.
#snapshot_id=$(aws ec2 describe-snapshots --filters Name=status,Values=completed --owner-ids self --query 'sort_by(Snapshots, &StartTime)[-1].SnapshotId' --output text)

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

# We need to wait for the volume to be ok.
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
echo -e "\nAttaching the volume $volume_id to the instance $testy_instance_id..."
attach=$(aws ec2 attach-volume --device xvdf --instance-id "$testy_instance_id" --volume-id "$volume_id")
if [ $? != 0 ]; then
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
    exit 1
fi

# Connect to the instance and mount the volume. Wait for some time after attaching the volume.
sleep 10

echo -e "\nCreating $backup_folder..."
sudo mkdir -p "$backup_folder"
echo "Mounting $virtual_device to $backup_folder..."
sudo mount $virtual_device $backup_folder;

# Call validate.
echo -e "\nValidating database..."
validation=0
if ! $backup_folder/srv/testy/workloads/sample/sample.sh validate; then
    validation=-1
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name validation --dimensions Instance="$testy_instance_id" --namespace "validation" --value "$validation")
    echo "Validation failed!"
    # Mark the snapshot as corrupted.
    aws ec2 create-tags --resources "$snapshot_id" --tags Key=analysis,Value=corrupted
else
    # Mark the snapshot as processed.
    # TODO: May not be useful since we will delete it.
    aws ec2 create-tags --resources "$snapshot_id" --tags Key=analysis,Value=clean
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name validation --dimensions Instance="$testy_instance_id" --namespace "validation" --value 1)

    # Delete snapshot.
    echo "Deleting snapshot $snapshot_id..."
    delete_snapshot=$(aws ec2 delete-snapshot --snapshot-id "$snapshot_id")
    if [ $? != 0 ]; then
        cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
        echo "Could not delete snapshot $snapshot_id"
    fi
fi

# When the validation is done, unmount and detach the volume.
echo -e "\nUnmounting $virtual_device..."
sudo umount "$virtual_device"
echo "Detaching $volume_id..."
detach_volume=$(aws ec2 detach-volume --volume-id "$volume_id" --query "State" --output text)
if [ $? != 0 ]; then
    cloudwatch=$(aws cloudwatch put-metric-data --metric-name aws-api-error --dimensions Instance="$testy_instance_id" --namespace "aws api error" --value -1)
    echo "Could not detach volume"
fi

# Delete the volume when fully detached.
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
