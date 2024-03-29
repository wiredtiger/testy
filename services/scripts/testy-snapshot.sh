#!/usr/bin/env bash

main() {
    local _device_name=/dev/xvdf
    local _mount_point=/mnt/backup
    local _validation_script=${_mount_point}${1}
    local _failure_dir=${3}
    local _failure_file=${4}

    local _aws_endpoint
    local _instance_id

    _aws_endpoint="http://169.254.169.254/latest/meta-data/"
    _instance_id=$(curl ${_aws_endpoint}/instance-id 2> /dev/null)

    echo "Starting database backup for instance '$_instance_id' ..."

    # Verify the instance exists.
    local _instance_exists
    _instance_exists=$(aws ec2 describe-instances --instance-id "$_instance_id")
    if [ -z "$_instance_exists" ]; then
        echo "Error: Instance '$_instance_id' not found."
        exit 1
    fi

    # Get number of volumes. If more than one volume is attached, it can mean a backup
    # is in progress or a volume has not been detached.
    local _volume_count
    get_volume_count "$_instance_id" _volume_count

    if [ -z "$_volume_count" ]; then
        echo "Error: Unable to retrieve volumes for instance '$_instance_id'."
        exit 1
    elif [ "$_volume_count" -eq 0 ]; then
        echo "Error: No volumes found for instance '$_instance_id'."
        exit 1
    elif [ "$_volume_count" -gt 1 ]; then
        echo "Error: Multiple volumes found for instance '$_instance_id'." \
             "A backup may be in progress."
        exit 1
    fi

    # Delete any previous snapshots that have been successfully validated.
    local _snapshot_ids
    _snapshot_ids=$(aws ec2 describe-snapshots --filters "Name=tag:Application,Values=testy" \
    "Name=tag:Validation,Values=success" "Name=tag:InstanceID,Values=$_instance_id" \
    --query "Snapshots[*].[SnapshotId]" --output text)
    for snapshot_id in $_snapshot_ids; do
        echo "Deleting snapshot '$snapshot_id' ..."
        if aws ec2 delete-snapshot --snapshot-id "$snapshot_id"; then
            echo "Deleted snapshot '$snapshot_id'."
        else
            echo "Error: Failed to delete snapshot '$snapshot_id'."
        fi
    done

    # Retrieve the tags from the instance.
    local _tags
    _tags=$(aws ec2 describe-instances --instance-ids "$_instance_id" \
        --query "Reservations[*].Instances[*].Tags[][]" --output json)
    # The json output from the aws cli call is not in the correct format for input to
    # an aws cli call. We need to strip the double quotes from the output and replace
    # the colons with equal signs.
    _tags="${_tags//\"/}"
    _tags="${_tags//:/=}"

    # Create a snapshot backup of the root volume.
    local _snapshot_id
    if ! create_snapshot "$_instance_id" "$_tags" _snapshot_id; then
        echo "Error: Unable to create a snapshot for instance '$_instance_id'."
        exit 1
    fi
    echo "Created backup snapshot '$_snapshot_id'."

    # Create a volume from the snapshot and if successful, attach it to the instance
    # and mount the device at the specificed mount point.
    local _availability_zone
    local _mount_device
    local _volume_id

    _availability_zone=$(curl ${_aws_endpoint}/placement/availability-zone 2> /dev/null)

    if create_volume_from_snapshot \
      "$_snapshot_id" "$_availability_zone" "$_instance_id" "$_tags" _volume_id
    then
        echo "Created backup volume '$_volume_id' from snapshot '$_snapshot_id'."
        if ! attach_volume "$_instance_id" "$_volume_id" "$_device_name" ||
               ! mount_device "$_mount_point" _mount_device; then
            # Delete volume and exit on failure.
            if delete_volume "$_volume_id" "$_mount_point" "$_mount_device"; then
                echo "Deleted volume '$_volume_id'."
            fi
            exit 1
        fi
    else
        echo "Error: Unable to create backup volume '$_volume_id' " \
             "from snapshot '$_snapshot_id'."
        exit 1
    fi

    # Validate database. Update the snapshot status on success/failure.
    aws ec2 create-tags --resources "$_snapshot_id" "$_volume_id" \
                        --tags Key=Validation,Value=none Key=InstanceID,Value="$_instance_id"

    echo "Running validation script '$_validation_script' on volume '$_volume_id'."
    ts=$(date +%s%3N)
    if validate_database "$_validation_script" "$_mount_point" "$_snapshot_id" "$_volume_id"; then
        echo "Successfully validated database backup snapshot '$_snapshot_id'."
        aws logs put-log-events --log-group-name testy-logs \
                                --log-stream-name testy-logs --log-events \
            timestamp=$ts,message="Backup snapshot ($_snapshot_id) validation succeeded for instance $_instance_id."
        # We can delete the snapshot now it has been validated.
        echo "Deleting snapshot '$_snapshot_id' ..."
        if aws ec2 delete-snapshot --snapshot-id "$_snapshot_id"; then
            echo "Deleted snapshot '$_snapshot_id'."
        else
            echo "Error: Failed to delete snapshot '$_snapshot_id'."
        fi
    else
        echo "Validation failed for database backup snapshot '$_snapshot_id'."
        aws logs put-log-events --log-group-name testy-logs \
                                --log-stream-name testy-logs --log-events \
            timestamp=$ts,message="Backup snapshot ($_snapshot_id) validation failed for instance $_instance_id."
    fi

    # Unmount the device, detach the volume and delete it when the validation is done. We
    # will keep the snapshot for debugging.
    if delete_volume "$_volume_id" "$_mount_point" "$_mount_device"; then
        echo "Deleted volume '$_volume_id'."
    fi
}

# Return the number of EBS volumes attached to the specified EC2 instance.
get_volume_count() {

    local _instance_id=$1
    local -n __volume_count=$2

    __volume_count=$(aws ec2 describe-volumes \
        --filters Name=attachment.instance-id,Values="$_instance_id" \
        --query "length(Volumes[*])" --output text)
}

# Returns the id of the root EBS volume for the specified EC2 instance.
get_root_volume_id() {

    local _instance_id=$1
    local -n __root_volume_id=$2

    local _root_device
    _root_device=$(aws ec2 describe-instances \
	    --instance-id "$_instance_id" \
	    --query "Reservations[*].Instances[*].RootDeviceName" \
	    --output text)

    if [ -z "$_root_device" ]; then
        echo "Error: No root device found for instance '$_instance_id'."
        return 1
    fi

    __root_volume_id=$(aws ec2 describe-volumes \
	    --filters Name=attachment.instance-id,Values="$_instance_id" \
	              Name=attachment.device,Values="$_root_device" \
	    --query "Volumes[*].{id:VolumeId}" \
	    --output text)
    
    if [ -z "$__root_volume_id" ]; then
        echo "Error: No root volume found for instance '$_instance_id'."
        return 1
    fi
}

# Create a snapshot backup of the root EBS volume for the specified EC2 instance. Returns
# the snapshot id on success.
create_snapshot() {

    local _instance_id=$1
    local _tags=$2
    local -n __snapshot_id=$3

    local _root_volume_id
    get_root_volume_id "$_instance_id" _root_volume_id

    # Create the snapshot with the specified tags.
    printf -v _tag_spec %s "ResourceType=snapshot, Tags=${_tags}"
    __snapshot_id=$(aws ec2 create-snapshot \
        --volume-id "$_root_volume_id" \
        --tag-specifications "${_tag_spec}" \
        --description "testy snapshot for $_instance_id" \
        --query "SnapshotId" \
        --output text)

    if [ -z "$__snapshot_id" ]; then
        echo "Error: Failed to create snapshot for instance '$_instance_id'."
        return 1
    fi

    # Update snapshot name.
    local _ltname
    _ltname=$(aws ec2 describe-instances --instance-ids "$_instance_id" \
        --query "Reservations[*].Instances[*].Tags[?Key==\`LaunchTemplateName\`].Value" \
        --output text)
    aws ec2 create-tags --resources "$__snapshot_id" \
        --tags "Key=Name,Value=testy-${_ltname}-${__snapshot_id//-/}"

    # Wait for the snapshot to complete and be ready for use. Return an error after timing out.
    local _snapshot_status=
    local _wait_timeout=10800
    local _wait_interval=10
    local _wait_time=0

    until [ "$_snapshot_status" == "completed" ]; do

        if [ $_wait_time -gt $_wait_timeout ]; then
            echo "Error: Waited $_wait_timeout seconds for snapshot '$__snapshot_id'" \
                 "to complete." 
            ts=$(date +%s%3N)
            aws logs put-log-events --log-group-name testy-logs \
                                    --log-stream-name snapshot-id --log-events \
            timestamp=$ts,message="Testy backup ($__snapshot_id) failed for instance $_instance_id."
            return 1
        fi

        sleep $_wait_interval
        _snapshot_status=$(aws ec2 describe-snapshots \
            --snapshot-ids "$__snapshot_id" \
		    --query "Snapshots[*].State" \
            --output text)
        ((_wait_time+=_wait_interval))
    done
    ts=$(date +%s%3N)
    aws logs put-log-events --log-group-name testy-logs \
                            --log-stream-name snapshot-id --log-events \
    timestamp=$ts,message="Testy backup ($__snapshot_id) succeeded for instance $_instance_id."
}

# Create a new EBS volume from the specified snapshot id that can be attached to
# an EC2 instance in the specified availability zone.
create_volume_from_snapshot() {

    local _snapshot_id=$1
    local _availability_zone=$2
    local _instance_id=$3
    local _tags=$4
    local -n __snapshot_volume_id=$5

    # Create the snapshot with the specified tags.
    printf -v _tag_spec %s "ResourceType=volume, Tags=${_tags}"
    __snapshot_volume_id=$(aws ec2 create-volume \
        --snapshot-id "$_snapshot_id" \
        --availability-zone "$_availability_zone" \
        --tag-specifications "${_tag_spec}" \
        --query "VolumeId" \
        --output text)

    if [ -z "$__snapshot_volume_id" ]; then
        echo "Error: Failed to create a volume from snapshot '$_snapshot_id' for" \
             "availability zone '$_availability_zone'."
        return 1
    fi

    # Update volume name.
    local _ltname
    _ltname=$(aws ec2 describe-instances --instance-ids "$_instance_id" \
        --query "Reservations[*].Instances[*].Tags[?Key==\`LaunchTemplateName\`].Value" \
        --output text)
    aws ec2 create-tags --resources "$__snapshot_volume_id" \
        --tags "Key=Name,Value=testy-${_ltname}-${__snapshot_volume_id//-/}"

    # Check that the volume status is "ok". Wait up to 1 hour.
    local _snapshot_volume_status=
    local _wait_timeout=3600
    local _wait_interval=10
    local _wait_time=0

    until [ "$_snapshot_volume_status" == "ok" ]; do

        if [ $_wait_time -gt $_wait_timeout ]; then
            echo "Error: Waited $_wait_timeout seconds for snapshot volume " \
                 "'$__snapshot_volume_id' to complete."
            return 1
        fi

        sleep $_wait_interval
        _snapshot_volume_status=$(aws ec2 describe-volume-status \
            --volume-ids "$__snapshot_volume_id" \
            --query "VolumeStatuses[*].VolumeStatus.Status" \
            --output text)
        ((_wait_time+=_wait_interval))
    done

    # Wait for the volume to become available for use.
    local _snapshot_volume_state=
    local _wait_time=0
    until [ "$_snapshot_volume_state" == "available" ]; do

        if [ $_wait_time -gt $_wait_timeout ]; then
            echo "Error: Waited $_wait_timeout seconds for snapshot volume " \
                 "'$__snapshot_volume_id' to be available for use."
            return 1
        fi

        sleep $_wait_interval
        _snapshot_volume_state=$(aws ec2 describe-volumes \
            --volume-ids "$__snapshot_volume_id" \
            --query "Volumes[*].State" \
            --output text)
        ((_wait_time+=_wait_interval))
    done
}

# Attach the specified EBS volume to the specified instance and expose it to the instance
# with the specified device name.
attach_volume() {
    
    local _instance_id=$1
    local _volume_id=$2
    local _device_name=$3

    # Attach the volume to the instance.
    local _volume_state
    _volume_state=$(aws ec2 attach-volume \
        --device "$_device_name" \
        --instance-id "$_instance_id" \
        --volume-id "$_volume_id" \
        --query "Volumes[*].State" \
        --output text)

    if [ -z "$_volume_state" ]; then
        echo "Error: Failed to attach volume '$_volume_id'."
        return 1
    fi

    # Wait for volume state to be in-use. Wait up to 1 hour.
    local _volume_state=
    local _wait_timeout=3600
    local _wait_interval=10
    local _wait_time=0

    until [ "$_volume_state" == "in-use" ]; do

        if [ $_wait_time -gt $_wait_timeout ]; then
            echo "Error: Volume '$_volume_id' failed to attach after $_wait_timeout seconds."
            return 1
        fi

        sleep $_wait_interval
        _volume_state=$(aws ec2 describe-volumes \
            --volume-ids "$_volume_id" \
            --query "Volumes[*].State" \
            --output text)
        ((_wait_time+=_wait_interval))
    done
}

# Detach the specified EBS volume from the specified instance.
detach_volume() {

    local _volume_id=$1

    # Detach the volume.
    if ! aws ec2 detach-volume --volume-id "$_volume_id" &> /dev/null; then
        echo "Error: Failed to detach volume '$_volume_id'."
        return 1
    fi

    # Wait for the volume to finish detaching and become available for further actions. Wait up to
    # 1 hour.
    local _volume_state=
    local _wait_timeout=3600
    local _wait_interval=10
    local _wait_time=0

    until [ "$_volume_state" == "available" ]; do

        if [ $_wait_time -gt $_wait_timeout ]; then
            echo "Error: Volume '$_volume_id' failed to detach after $_wait_timeout seconds."
            return 1
        fi

        sleep $_wait_interval
        _volume_state=$(aws ec2 describe-volumes \
            --volume-ids "$_volume_id" \
            --query "Volumes[*].State" \
            --output text)
        ((_wait_time+=_wait_interval))

    done
}
    
# Mount the EBS volume exposed by the specified device name at the specified mount point.
mount_device()
{
    local _mount_point=$1
    local -n __mount_device=$2

    # Get the root device.
    local _root_device
    _root_device=$(findmnt -n -o SOURCE /)

    # Get the filesystem of the root device.
    local _fs
    _fs=$(sudo blkid -o value -s TYPE "$_root_device")

    # Get all devices of this filesystem type.
    local _devices
    _devices=$(sudo blkid -t TYPE="$_fs" -o device)

    # Find the unmounted device.
    for device in ${_devices[@]}; do
        if ! findmnt -n "$device" &> /dev/null; then
             __mount_device=$device
             break
        fi
    done

    # Check that device is present.
    if [ -z "$__mount_device" ]; then
        echo "Error: No unmounted device found."
        return 1
    fi

    # Check that mount point is not in use.
    if mountpoint "$_mount_point" &> /dev/null; then
        echo "Error: Mount point '$_mount_point' is in use."
        return 1
    fi

    # XFS file systems need a special mount option if the UUID is not present.
    local _mount_options="rw"
    if [ "$_fs" == "xfs" ]; then
        _mount_options+=",nouuid"
    fi

    # Mount device.
    sudo mkdir -p "$_mount_point"
    if sudo mount -t "$_fs" -o "$_mount_options" "$__mount_device" "$_mount_point"; then
        return 0
    fi

    echo "Error: Failed to mount device '$__mount_device'."
    return 1
}

# Unmount the EBS volume exposed by the specified device name at the specified mount point.
unmount_device()
{
    local _mount_point=$1
    local _mount_device=$2

    # Verify that the mount point is in use.
    if ! mountpoint "$_mount_point" &> /dev/null; then
        echo "Error: Mount point '$_mount_point' is not a mountpoint."
        return 1
    fi

    # Check that device is present.
    if ! test -b "$_mount_device"; then
        echo "Error: '$_mount_device' does not exist."
        return 1
    fi

    # Unmount device.
    if ! sudo umount "$_mount_device"; then
        echo "Error: Failed to unmount device '$_mount_device'."
        return 1
    fi
}

# Validate database. Update the snapshot and volume validation status while in progress
# and on successful or failed completion.
validate_database() {

    local _validation_script=$1
    local _mount_point=$2
    local _snapshot_id=$3
    local _volume_id=$4

    aws ec2 create-tags --resources "$_snapshot_id" "$_volume_id" \
                        --tags Key=Validation,Value=incomplete

    if "$_validation_script" validate $_mount_point; then
        aws ec2 create-tags --resources "$_snapshot_id" "$_volume_id" \
                            --tags Key=Validation,Value=success
        return 0
    fi
        
    aws ec2 create-tags --resources "$_snapshot_id" "$_volume_id" \
                        --tags Key=Validation,Value=failed
    
    # Rename failure files to their associated snapshot id.
    sudo mv -v "${_failure_dir}/${_failure_file}" "${_failure_dir}/${_snapshot_id}.txt"
    echo "Validation failed for ${_snapshot_id}, logs saved to ${_failure_dir}/${_snapshot_id}.txt" 
    return 1
}

# Unmount the specified device, detach the specified volume and delete it.
delete_volume() {

    local _volume_id=$1
    local _mount_point=$2
    local _mount_device=$3

    # Unmount the device.
    if [ -n "$_mount_device" ]; then
        unmount_device "$_mount_point" "$_mount_device"
    fi

    # Detach the volume.
    detach_volume "$_volume_id"

    # Delete volume.
    if ! aws ec2 delete-volume --volume-id "$_volume_id"; then
        echo "Error: Failed to delete volume '$_volume_id'."
        return 1
    fi
}

# Run main function.
main "$@"
