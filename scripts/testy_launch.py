import json, sys, time
from itertools import cycle
from invoke import run as local
from invoke.exceptions import Exit

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
        --filters 'Name=tag:Application,Values=testy' \
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

def set_tag_for_resource(resource_id, key, value):
    result = local(f"aws ec2 create-tags \
        --resources {resource_id} \
        --tags 'Key={key},Value={value}'", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)

def get_tag_value_from_resource(resource_id, key):
    result = local(f"aws ec2 describe-tags \
        --filters 'Name=resource-id,Values={resource_id}' \
        --query 'Tags[?Key==`{key}`].Value' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    value = result.stdout.strip()
    if not value:
        raise Exit(f"Unable to retrieve value for key '{key}' from resource '{resource_id}'")
    return value

def get_volume_id_from_instance(instance_id):
    result = local(f"aws ec2 describe-volumes \
        --filters Name=attachment.instance-id,Values={instance_id} \
        --query 'Volumes[*].VolumeId' --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    value = result.stdout.strip()
    if not value:
        raise Exit(f"Unable to retrieve volume ID for instance '{instance_id}'")
    return value

def launch_template_exists(launch_template_name):
    result = local(f"aws ec2 describe-launch-templates \
        --launch-template-names {launch_template_name} \
        --filters 'Name=tag:Application,Values=testy' \
        --query 'LaunchTemplates[*].LaunchTemplateName' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    return True if result.stdout.strip() else False

def register_image_from_snapshot(image_name, architecture, snapshot_id):
    result = local("aws ec2 register-image \
        --name " + image_name + " \
        --root-device-name /dev/xvda \
        --block-device-mappings \
          '[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"SnapshotId\":\"" + snapshot_id + "\"}}]' \
        --architecture " + architecture + " \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    image_id = result.stdout.strip()
    return image_id

def snapshot_exists(snapshot_id):
    result = local(f"aws ec2 describe-snapshots \
        --snapshot-ids {snapshot_id} \
        --filters 'Name=tag:Application,Values=testy' \
        --query 'Snapshots[*].SnapshotId' \
        --output text", hide=True, warn=True)
    if result.stderr:
        raise Exit(result.stderr)
    return True if result.stdout.strip() else False

def wait_on_status_check(instance_id):
    max_retries = 60
    sleep_time = 10
    retry = 0

    timer = cycle(['\\', '|', '/', '—'])
    msg = f"Waiting for the status check to complete. This may take several minutes ..."
    print("", end=f"{msg}\r", flush=True)

    while retry < max_retries:

        # AWS reports two statuses on EC2 instances, a "system status" and an "instance
        # status", to identify hardware and software issues. When an instance is launched,
        # the below aws cli call returns an empty list ([]) until the instance is running.
        # Once the instance is running, the cli returns a nested list containing a text
        # description of the two statuses, e.g. [['initializing', 'initializing']]. The
        # instance is ready for use when both status checks have passed, which is reflected
        # by the cli output of [['ok', 'ok']].
        result = local(f"aws ec2 describe-instance-status \
            --instance-ids {instance_id} \
            --query 'InstanceStatuses[*].[InstanceStatus.Status,SystemStatus.Status]' \
            --output json", hide=True, warn=True)
        if result.stderr:
            raise Exit(result.stderr)

        status = json.loads(result.stdout)
        if (len(status) == 0 or len(status[0]) != 2):
            continue
        if status[0][0] == "ok" and status[0][1] == "ok":
            print("", end=f"{msg} Success!\n", flush=True)
            break
        retry += 1
        for _ in range (sleep_time):
            print("", end=f"{msg} {next(timer)}\r", flush=True)
            time.sleep(1)

    else:
        print("", end=f"{msg} Timed out.\n", flush=True)
        raise Exit(f"The status check failed to complete successfully after "
            f"{max_retries*sleep_time} seconds. Please check the AWS console.")

# The following two functions are called from the fabfile and implement launching an
# instance in AWS EC2 from either a launch template (analogous to an Evergreen "distro")
# or from a snapshot ID. The functions return a python dictionary that contains information
# relevant to the user executing the fab commands. The dictionary always includes the exit
# status of the function, which is zero on success and non-zero on failure. On success,
# the dictionary contains the necessary information for the user to log in to the
# instance via ssh and identify the instance on the AWS console. On failure, the dictionary
# contains a user-friendly error message.

# Launch an AWS instance given a distro.
def launch_from_distro(distro, iam_profile):

    if not launch_template_exists(distro):
        return {"status": 1, "msg": f"The distro '{distro}' does not exist."}

    print("", end=f"\rCreating a {distro} testy server in EC2 ... ", flush=True)
    hostname = None
    user = None

    try:
        # Launch an EC2 instance based on a template.
        result = local(f"aws ec2 run-instances \
            --launch-template LaunchTemplateName={distro} \
            --query Instances[*].InstanceId \
            --output text", hide=True, warn=True)
        if result.stderr:
            print("Failed.", flush=True)
            raise Exit(result.stderr)

        print("Success!", flush=True)
        instance_id = result.stdout.strip()
        wait_on_status_check(instance_id)

        # Attach IAM profile if requested.
        if iam_profile:
            result = local(f"aws iam get-role \
                --role-name {iam_profile} \
                --output-text", hide=True, warn=True)

            if result.stderr:
                print(f"The IAM profile '{iam_profile}' does not exist.", flush=True)

            else:
                result = local(f"aws ec2 associate-iam-instance-profile \
                    --instance-id {instance_id} \
                    --iam-instance-profile Name={iam_profile}", hide=True, warn=True)
                if result.stderr:
                    print(f"Failed at attaching the IAM profile '{iam_profile}'.", flush=True)
                else:
                    print(f"The IAM profile '{iam_profile}' has been successfully attached!", flush=True)

        # Add 'Name' tags for the new instance and volume.
        volume_id = get_volume_id_from_instance(instance_id)
        instance_name = f"testy-{distro}-{instance_id.replace('-','')}"
        set_tag_for_resource(instance_id, "Name", instance_name)
        set_tag_for_resource(volume_id, "Name", f"testy-{distro}-{volume_id.replace('-','')}")

        hostname = get_hostname_for_instance(instance_id)
        user = get_tag_value_from_resource(instance_id, "User")

    except Exception as e:
        return {"status": 1, "msg": str(e).strip()}

    return {"status": 0, "user": user, "hostname": hostname,
        "instance_id": instance_id, "instance_name": instance_name}

# Launch an AWS instance from a snapshot ID.
def launch_from_snapshot(snapshot_id):

    if not snapshot_exists(snapshot_id):
        return {"status": 1, "msg": f"The snapshot '{snapshot_id}' does not exist."}

    print("", end=f"\rCreating a testy server from snapshot '{snapshot_id}' ... ", flush=True)
    hostname = None
    user = None

    try:
        snapshot_status = get_snapshot_status(snapshot_id)
        if snapshot_status != 'completed':
            print("Failed.", flush=True)
            raise Exit(f"The snapshot '{snapshot_id}' is incomplete ({snapshot_status}).")

        image_name = f"image-{snapshot_id}"
        image_id = get_image_id(image_name)

        if not image_id:
            architecture = get_tag_value_from_resource(snapshot_id, "Architecture")
            image_id = register_image_from_snapshot(image_name, architecture, snapshot_id)

        # Launch an EC2 instance based on a template and an image ID.
        ltname = get_tag_value_from_resource(snapshot_id, "LaunchTemplateName")
        result = local(f"aws ec2 run-instances \
            --launch-template LaunchTemplateName={ltname} \
            --image-id {image_id} \
            --query Instances[*].InstanceId \
            --output text", hide=True, warn=True)
        if result.stderr:
            raise Exit(result.stderr)

        print("Success!", flush=True)
        instance_id = result.stdout.strip()

        # Always deregister the image.
        result = local(f"aws ec2 deregister-image --image-id {image_id}")
        if result.stderr:
            # We don't need to exit if this call fails.
            print(f"Error deregistering image '{image_name}': {result.stderr}")

        wait_on_status_check(instance_id)

        # Add 'Name' tags for the new instance and volume.
        volume_id = get_volume_id_from_instance(instance_id)
        instance_name = f"testy-{ltname}-{instance_id.replace('-','')}"
        set_tag_for_resource(instance_id, "Name", instance_name)
        set_tag_for_resource(volume_id, "Name", f"testy-{ltname}-{volume_id.replace('-','')}")

        hostname = get_hostname_for_instance(instance_id)
        user = get_tag_value_from_resource(instance_id, "User")

    except Exception as e:
        return {"status": 1, "msg": str(e).strip()}

    return {"status": 0, "user": user, "hostname": hostname,
        "instance_id": instance_id, "instance_name": instance_name}

if __name__ == "__main__":

    globals()[sys.argv[1]](*sys.argv[2:])
