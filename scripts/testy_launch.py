import time
from invoke import run as local
from invoke.exceptions import Exit
import sys

def get_architecture_from_platform(platform):
    print(f"Retrieving architecture from {platform}...")
    result = local(f"aws ec2 describe-launch-templates \
        --launch-template-name {platform} \
        --query 'LaunchTemplates[*].Tags[?Key==`Architecture`].Value[]' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
    architecture = result.stdout.strip()
    if not architecture:
        raise Exit(f"Error: The architecture could not be retrieved from the platform {platform}")
    print(f"Architecture: {architecture}")
    return architecture

def get_default_user_from_platform(platform):
    print(f"Retrieving default user from {platform}...")
    result = local(f"aws ec2 describe-launch-templates \
        --launch-template-name {platform} \
        --query 'LaunchTemplates[*].Tags[?Key==`User`].Value[]' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
    user = result.stdout.strip()
    if not user:
        raise Exit(f"Error: The user could not be retrieved from the platform {platform}")
    print(f"User: {user}")
    return user

def get_hostname_from_instance(instance_id):
    print(f"Retrieving hostname from {instance_id}...")
    result = local(f"aws ec2 describe-instances \
        --instance-ids {instance_id} \
        --query 'Reservations[*].Instances[*].PublicDnsName' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
    hostname = result.stdout.strip()
    print(f"Hostname: {hostname}")
    return hostname

def get_platform_from_snapshot(snapshot_id):
    print(f"Retrieving platform from {snapshot_id}...")
    result = local(f"aws ec2 describe-snapshots \
        --snapshot-ids {snapshot_id} \
        --query 'Snapshots[*].Tags[?Key==`Platform`].Value[]' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
    platform = result.stdout.strip()
    print(f"Platform: {platform}")
    if not platform:
        raise Exit(f"Error: The platform could not be retrieved from the snapshot {snapshot_id}")
    return platform

def image_exists(image_name):
    print(f"Checking if image {image_name} exists...")
    result = local(f"aws ec2 describe-images \
        --filters \"Name=name,Values={image_name}\" \
        --query 'Images[*].ImageId' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
    image_id = result.stdout.strip()
    print(f"Image id: {image_id}")
    return image_id

def get_platforms():
    print("Retrieving platforms...")
    result = local("aws ec2 describe-launch-templates \
        --query 'LaunchTemplates[*].LaunchTemplateName' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
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
        raise Exit(f"Error: {result.stderr}")
    snapshots = result.stdout.strip()
    print(f"Snapshots: {snapshots}")
    return snapshots

def get_snapshot_status(snapshot_id):
    print(f"Retrieving status of snapshot {snapshot_id}...")
    result = local(f"aws ec2 describe-snapshots \
        --snapshot-ids {snapshot_id} \
        --query 'Snapshots[*].State' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
    snapshot_status = result.stdout.strip()
    print(f"Snapshot status: {snapshot_status}")
    return snapshot_status

def platform_exists(platform):
    print(f"Checking if platform {platform} exists...")
    result = local(f"aws ec2 describe-launch-templates \
        --launch-template-names {platform} \
        --filter 'Name=tag:Application,Values=testy' \
        --query 'LaunchTemplates[*].LaunchTemplateName' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
    print(f"Platform exists: {result.stdout.strip()}")
    return result.stdout

def register_image_from_snapshot(image_name, architecture, snapshot_id):
    print(f"Registering image {image_name} with architecture {architecture} and snapshot {snapshot_id}...")
    result = local("aws ec2 register-image \
        --name " + image_name + " \
        --root-device-name /dev/xvda \
        --block-device-mappings '[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"SnapshotId\":\"" + snapshot_id + "\"}}]' \
        --architecture " + architecture + " \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
    image_id = result.stdout.strip()
    print(f"Image id: {image_id}")
    return image_id

def snapshot_exists(snapshot_id):
    print(f"Checking if snapshot {snapshot_id} exists...")
    result = local(f"aws ec2 describe-snapshots \
        --filter 'Name=tag:Application,Values=testy' \
        --query 'Snapshots[*].SnapshotId' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
    print(f"Snapshot exists: {result.stdout.strip()}")
    return result.stdout

def wait_instance_running(instance_id):
    print(f"Waiting for the instance {instance_id} to be running...")
    state = None
    expected_state = "running"
    max_retries = 10
    num_retry = 0

    while num_retry < max_retries:
        result = local(f"aws ec2 describe-instances \
            --instance-ids {instance_id} \
            --query 'Reservations[*].Instances[*].State.Name' \
            --output text", hide=True, warn=True)
        if result.stderr:
            raise Exit(f"Error: {result.stderr}")
        state = result.stdout.strip()
        print(f"State: {state}")
        if state != expected_state:
            num_retry += 1
            time.sleep(5)
        else:
            break
    
    if state != expected_state and num_retry >= max_retries:
        raise Exit(f"Timeout: the instance {instance_id} is still in the state {state}")

def testy_launch(platform = None):

    user = None
    hostname = None

    print(f"Platform name: {platform}")

    if not platform or platform == 'None':
        # Print all the available platform.
        print("The available platforms are:")
        platforms = get_platforms()
        for platform in platforms.split():
            print(f"- {platform}")
        return user, hostname
    
    # Check the platform exists.
    if not platform_exists(platform):
        raise Exit(f"The platform '{platform}' does not exist")
    
    # Spawn an instance.
    result = local(f"aws ec2 run-instances \
        --launch-template LaunchTemplateName={platform} \
        --tag-specifications 'ResourceType=instance, Tags=[{{Key=Application,Value=testy}}, \
            {{Key=Platform,Value={platform}}}]' \
        --query Instances[*].InstanceId \
        --output text", hide=True, warn=True)
    if result.stderr:
        print(f"Error: {result.stderr}")
    instance_id = result.stdout.strip()

    # Retrieve the use and the hostname.
    hostname = get_hostname_from_instance(instance_id)
    user = get_default_user_from_platform(platform)

    # Wait for the instance to be running.
    wait_instance_running(instance_id)

    print("Connect to the new instance with:")
    print(f"ssh {user}@{hostname}")

    return user, hostname

def testy_launch_snapshot(snapshot_id = None):

    print(f"Snapshot: {snapshot_id}")

    if not snapshot_id or snapshot_id == 'None':
        # Print all the available snapshots.
        print("The available snapshots are:")
        snapshots = get_snapshots()
        for snapshot in snapshots.split():
            print(f"- {snapshot}")
        return
    
    # Check the snapshot exists.
    if not snapshot_exists(snapshot_id):
        raise Exit(f"The snapshot '{snapshot_id}' does not exist")

    # Check the snapshot has the right status.
    snapshot_status = get_snapshot_status(snapshot_id)
    if snapshot_status != 'completed':
        raise Exit(f"The snapshot '{snapshot_id}' is incomplete ({snapshot_status}).")

    # Retrieve the platform from the snapshot.
    platform = get_platform_from_snapshot(snapshot_id)

    # Generate the image name.
    image_name = f"{platform}-{snapshot_id}"

    # Check if the AMI already exists.
    image_id = image_exists(image_name)
    if not image_id:
        # Retrieve the architecture from the platform's tags.
        architecture = get_architecture_from_platform(platform)
        
        # Register the image.
        image_id = register_image_from_snapshot(image_name, architecture, snapshot_id)

    # Spawn an instance.
    result = local(f"aws ec2 run-instances \
        --launch-template LaunchTemplateName={platform} \
        --tag-specifications 'ResourceType=instance, Tags=[{{Key=Application,Value=testy}}, \
            {{Key=Platform,Value={platform}}}]' \
        --image-id {image_id} \
        --query Instances[*].InstanceId \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(f"Error: {result.stderr}")
    instance_id = result.stdout.strip()

    # Always deregister the image.
    print(f"Deregistering image {image_id}...")
    result = local(f"aws ec2 deregister-image --image-id {image_id}")
    if result.stderr:
        # We don't need to exit if this call fails.
        print(f"Error: {result.stderr}")

    # Retrieve the use and the hostname.
    hostname = get_hostname_from_instance(instance_id)
    user = get_default_user_from_platform(platform)

    # Wait for the instance to be running.
    wait_instance_running(instance_id)

    print("Connect to the new instance with:")
    print(f"ssh {user}@{hostname}")

if __name__ == "__main__":

    globals()[sys.argv[1]](*sys.argv[2:])
