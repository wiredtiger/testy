import time
from invoke import run as local
from invoke.exceptions import Exit
import sys

def get_hostname_for_instance(instance_id):
    result = local(f"aws ec2 describe-instances \
        --instance-ids {instance_id} \
        --query 'Reservations[*].Instances[*].PublicDnsName' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    hostname = result.stdout.strip()
    return hostname

def get_image_id(image_name):
    result = local(f"aws ec2 describe-images \
        --filters \"Name=name,Values={image_name}\" \
        --query 'Images[*].ImageId' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    image_id = result.stdout.strip()
    return image_id

# Get all the available launch templates and return the result as a list.
def get_launch_templates():
    result = local("aws ec2 describe-launch-templates \
        --query 'LaunchTemplates[*].LaunchTemplateName' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    launch_templates = result.stdout.strip()
    return launch_templates.split()

# Get all the available snapshots and return the result as a list.
def get_snapshots():
    result = local("aws ec2 describe-snapshots \
        --filter 'Name=tag:Application,Values=testy' \
        --query 'Snapshots[*].SnapshotId' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    snapshots = result.stdout.strip()
    return snapshots.split()

def get_snapshot_status(snapshot_id):
    result = local(f"aws ec2 describe-snapshots \
        --snapshot-ids {snapshot_id} \
        --query 'Snapshots[*].State' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    snapshot_status = result.stdout.strip()
    return snapshot_status

def get_value_from_launch_template(launch_template_name, key):
    result = local(f"aws ec2 describe-launch-templates \
        --launch-template-name {launch_template_name} \
        --query 'LaunchTemplates[*].Tags[?Key==`{key}`].Value[]' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    value = result.stdout.strip()
    if not value:
        raise Exit(f"Error: Unable to retrieve '{key}' for '{launch_template_name}'")
    return value

def get_value_from_snapshot(snapshot_id, key):
    result = local(f"aws ec2 describe-snapshots \
        --snapshot-ids {snapshot_id} \
        --query 'Snapshots[*].Tags[?Key==`{key}`].Value[]' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    value = result.stdout.strip()
    if not value:
        raise Exit(f"Error: Unable to retrieve '{key}' for '{snapshot_id}'")
    return value

def launch_template_exists(launch_template_name):
    result = local(f"aws ec2 describe-launch-templates \
        --launch-template-names {launch_template_name} \
        --filter 'Name=tag:Application,Values=testy' \
        --query 'LaunchTemplates[*].LaunchTemplateName' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    return True if result.stdout.strip() else False

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

def set_instance_name(instance_id, name):
    result = local(f"aws ec2 create-tags \
        --resources {instance_id} \
        --tags Key=Name,Value={name}", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)

def snapshot_exists(snapshot_id):
    result = local(f"aws ec2 describe-snapshots \
        --snapshot-ids {snapshot_id} \
        --filter 'Name=tag:Application,Values=testy' \
        --query 'Snapshots[*].SnapshotId' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    return True if result.stdout.strip() else False

def wait_instance_running(instance_id):
    print(f"Waiting for the EC2 instance '{instance_id}' to be running ...")
    # Code 16 corresponds to "running".
    expected_state = "16"
    max_retries = 20
    num_retry = 0

    while num_retry < max_retries:
        result = local(f"aws ec2 describe-instance-status \
            --instance-ids {instance_id} \
            --query 'InstanceStatuses[*].InstanceState.Code' \
            --output text", hide=True, warn=True)
        if result.stderr:
            raise Exit(result.stderr)
        state = result.stdout.strip()
        if state != expected_state:
            num_retry += 1
            time.sleep(10)
        else:
            break
    else:
        raise Exit(f"Timeout: the instance {instance_id} is not running.")

def wait_instance_status_check_ok(instance_id):
    print(f"Waiting for the EC2 instance '{instance_id}' to pass the status check ...")
    max_retries = 20
    num_retry = 0

    while num_retry < max_retries:
        result = local(f"aws ec2 describe-instance-status \
            --instance-ids {instance_id} \
            --query 'InstanceStatuses[*].[InstanceStatus.Status,SystemStatus.Status]' \
            --output text", hide=True, warn=True)
        if result.stderr:
            raise Exit(result.stderr)
        checks = result.stdout.strip().split()

        while True:
            if not len(checks):
                return
            if checks[0] != 'ok':
                break
            checks.pop(0)
        num_retry += 1
        time.sleep(10)
    else:
        raise Exit(f"Timeout: the instance {instance_id} has not passed the status check yet.")

# Launch an AWS instance given a distro.
# This function returns a dictionary with a 'status' field that is set to 0 only when the instance
# has been launched successfully. In that case, the dictionary contains a 'user' and 'host' fields.
# Upon failure, the 'status' field is not 0 and the 'msg' field contains the error message.
def testy_launch(distro):

    user = None
    hostname = None

    try:
        if not launch_template_exists(distro):
            raise Exit(f"The distro '{distro}' does not exist.")
        
        # Launch an EC2 instance based on a template.
        result = local(f"aws ec2 run-instances \
            --launch-template LaunchTemplateName={distro} \
            --tag-specifications 'ResourceType=instance, Tags=[{{Key=Application,Value=testy}}, \
                {{Key=LaunchTemplateName,Value={distro}}}]' \
            --query Instances[*].InstanceId \
            --output text", hide=True, warn=True)
        if result.stderr:
            raise Exit(result.stderr)
        instance_id = result.stdout.strip()

        set_instance_name(instance_id, f"testy-{distro}-{instance_id}")

        hostname = get_hostname_for_instance(instance_id)
        user = get_value_from_launch_template(distro, 'User')

        wait_instance_running(instance_id)
        wait_instance_status_check_ok(instance_id)
    except Exception as e:
        return {"status": 1, "msg": str(e).strip()}

    return {"status": 0, "user": user, "hostname": hostname}

# Launch an AWS instance given a snapshot ID.
# This function returns a dictionary with a 'status' field that is set to 0 only when the instance
# has been launched successfully. In that case, the dictionary contains a 'user' and 'host' fields.
# Upon failure, the 'status' field is not 0 and the 'msg' field contains the error message.
def testy_launch_snapshot(snapshot_id):

    try:
        if not snapshot_exists(snapshot_id):
            raise Exit(f"The snapshot {snapshot_id} does not exist.")

        snapshot_status = get_snapshot_status(snapshot_id)
        if snapshot_status != 'completed':
            raise Exit(f"The snapshot '{snapshot_id}' is incomplete ({snapshot_status}).")

        launch_template_name = get_value_from_snapshot(snapshot_id, 'LaunchTemplateName')
        image_name = f"{launch_template_name}-{snapshot_id}"
        image_id = get_image_id(image_name)

        if not image_id:
            architecture = get_value_from_launch_template(launch_template_name, 'Architecture')
            image_id = register_image_from_snapshot(image_name, architecture, snapshot_id)

        # Launch an EC2 instance based on a template and an image ID.
        result = local(f"aws ec2 run-instances \
            --launch-template LaunchTemplateName={launch_template_name} \
            --tag-specifications 'ResourceType=instance, Tags=[{{Key=Application,Value=testy}}, \
                {{Key=LaunchTemplateName,Value={launch_template_name}}}]' \
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

        set_instance_name(instance_id, f"testy-{launch_template_name}-{snapshot_id}")

        hostname = get_hostname_for_instance(instance_id)
        user = get_value_from_launch_template(launch_template_name, 'User')

        wait_instance_running(instance_id)
    except Exception as e:
        return {"status": 1, "msg": str(e).strip()}

    return {"status": 0, "user":user, "hostname":hostname}

if __name__ == "__main__":

    globals()[sys.argv[1]](*sys.argv[2:])
