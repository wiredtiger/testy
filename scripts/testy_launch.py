import time
from invoke import run as local
from invoke.exceptions import Exit
import sys

def get_architecture_from_platform(platform):
    result = local(f"aws ec2 describe-launch-templates \
        --launch-template-name {platform} \
        --query 'LaunchTemplates[*].Tags[?Key==`Architecture`].Value[]' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    architecture = result.stdout.strip()
    if not architecture:
        raise Exit(f"Error: The architecture could not be retrieved from the platform {platform}")
    return architecture

def get_default_user_from_platform(platform):
    result = local(f"aws ec2 describe-launch-templates \
        --launch-template-name {platform} \
        --query 'LaunchTemplates[*].Tags[?Key==`User`].Value[]' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    user = result.stdout.strip()
    if not user:
        raise Exit(f"Error: The user could not be retrieved from the platform {platform}")
    return user

def get_hostname_from_instance(instance_id):
    result = local(f"aws ec2 describe-instances \
        --instance-ids {instance_id} \
        --query 'Reservations[*].Instances[*].PublicDnsName' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    hostname = result.stdout.strip()
    return hostname

def get_platform_from_snapshot(snapshot_id):
    result = local(f"aws ec2 describe-snapshots \
        --snapshot-ids {snapshot_id} \
        --query 'Snapshots[*].Tags[?Key==`LaunchTemplateName`].Value[]' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    platform = result.stdout.strip()
    if not platform:
        raise Exit(f"Error: The platform could not be retrieved from the snapshot {snapshot_id}")
    return platform

def image_exists(image_name):
    result = local(f"aws ec2 describe-images \
        --filters \"Name=name,Values={image_name}\" \
        --query 'Images[*].ImageId' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    image_id = result.stdout.strip()
    return image_id

def get_platforms():
    print("Retrieving platforms...")
    result = local("aws ec2 describe-launch-templates \
        --query 'LaunchTemplates[*].LaunchTemplateName' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    platforms = result.stdout.strip()
    print(f"Platforms: {platforms}")
    return platforms

def get_snapshots():
    print("Retrieving snapshots...")
    result = local("aws ec2 describe-snapshots \
        --filter 'Name=tag:Application,Values=testy' \
        --query 'Snapshots[*].SnapshotId' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    snapshots = result.stdout.strip()
    print(f"Snapshots: {snapshots}")
    return snapshots

def get_snapshot_status(snapshot_id):
    result = local(f"aws ec2 describe-snapshots \
        --snapshot-ids {snapshot_id} \
        --query 'Snapshots[*].State' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    snapshot_status = result.stdout.strip()
    return snapshot_status

def platform_exists(platform):
    result = local(f"aws ec2 describe-launch-templates \
        --launch-template-names {platform} \
        --filter 'Name=tag:Application,Values=testy' \
        --query 'LaunchTemplates[*].LaunchTemplateName' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)

def register_image_from_snapshot(image_name, architecture, snapshot_id):
    result = local("aws ec2 register-image \
        --name " + image_name + " \
        --root-device-name /dev/xvda \
        --block-device-mappings '[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"SnapshotId\":\"" + snapshot_id + "\"}}]' \
        --architecture " + architecture + " \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    image_id = result.stdout.strip()
    return image_id

def snapshot_exists(snapshot_id):
    result = local(f"aws ec2 describe-snapshots \
        --snapshot-ids {snapshot_id} \
        --filter 'Name=tag:Application,Values=testy' \
        --query 'Snapshots[*].SnapshotId' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)

def wait_instance_running(instance_id):
    print(f"Waiting for the EC2 instance '{instance_id}' to be running ...")
    state = None
    # Code 16 corresponds to "running".
    expected_state = "16"
    max_retries = 20
    num_retry = 0

    while num_retry < max_retries:
        result = local(f"aws ec2 describe-instances \
            --instance-ids {instance_id} \
            --query 'Reservations[*].Instances[*].State.Code' \
            --output text", hide=True, warn=True)
        if result.stderr:
            raise Exit(result.stderr)
        state = result.stdout.strip()
        if state != expected_state:
            num_retry += 1
            time.sleep(5)
        else:
            break
    else:
        raise Exit(f"Timeout: the instance {instance_id} is not running.")

# Launch an AWS instance given a platform.
# This function returns a dictionary with a 'status' field that is set to 0 only when the instance
# has been launched successfully. In that case, the dictionary contains a 'user' and 'host' fields.
# Upon failure, the 'status' field is not 0 and the 'msg' field contains the error message.
def testy_launch(platform):

    user = None
    hostname = None

    try:
        platform_exists(platform)
        
        # Launch an EC2 instance based on a template.
        result = local(f"aws ec2 run-instances \
            --launch-template LaunchTemplateName={platform} \
            --tag-specifications 'ResourceType=instance, Tags=[{{Key=Application,Value=testy}}, \
                {{Key=LaunchTemplateName,Value={platform}}}]' \
            --query Instances[*].InstanceId \
            --output text", hide=True, warn=True)
        if result.stderr:
            raise Exit(result.stderr)
        instance_id = result.stdout.strip()

        hostname = get_hostname_from_instance(instance_id)
        user = get_default_user_from_platform(platform)

        wait_instance_running(instance_id)
    except Exception as e:
        return {"status": 1, "msg": str(e).strip()}

    return {"status": 0, "user":user, "hostname":hostname}

# Launch an AWS instance given a snapshot ID.
# This function returns a dictionary with a 'status' field that is set to 0 only when the instance
# has been launched successfully. In that case, the dictionary contains a 'user' and 'host' fields.
# Upon failure, the 'status' field is not 0 and the 'msg' field contains the error message.
def testy_launch_snapshot(snapshot_id):

    try:
        snapshot_exists(snapshot_id)

        snapshot_status = get_snapshot_status(snapshot_id)
        if snapshot_status != 'completed':
            raise Exit(f"The snapshot '{snapshot_id}' is incomplete ({snapshot_status}).")

        platform = get_platform_from_snapshot(snapshot_id)
        image_name = f"{platform}-{snapshot_id}"
        image_id = image_exists(image_name)

        if not image_id:
            architecture = get_architecture_from_platform(platform)
            image_id = register_image_from_snapshot(image_name, architecture, snapshot_id)

        # Launch an EC2 instance based on a template and an image ID.
        result = local(f"aws ec2 run-instances \
            --launch-template LaunchTemplateName={platform} \
            --tag-specifications 'ResourceType=instance, Tags=[{{Key=Application,Value=testy}}, \
                {{Key=LaunchTemplateName,Value={platform}}}]' \
            --image-id {image_id} \
            --query Instances[*].InstanceId \
            --output text", hide=True, warn=True)
        if result.stderr:
            raise Exit(result.stderr)
        instance_id = result.stdout.strip()

        # Always deregister the image.
        result = local(f"aws ec2 deregister-image --image-id {image_id}")
        if result.stderr:
            # We don't need to exit if this call fails.
            print(f"Error: {result.stderr}")

        # Retrieve the user and the hostname.
        hostname = get_hostname_from_instance(instance_id)
        user = get_default_user_from_platform(platform)

        # Wait for the instance to be running.
        wait_instance_running(instance_id)
    except Exception as e:
        return {"status": 1, "msg": str(e).strip()}

    return {"status": 0, "user":user, "hostname":hostname}

if __name__ == "__main__":

    globals()[sys.argv[1]](*sys.argv[2:])
