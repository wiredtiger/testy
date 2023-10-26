# fabfile.py
# Remote management commands for testy: A WiredTiger 24/7 workload testing framework.

import configparser as cp, os, re
from contextlib import redirect_stdout
from invoke.exceptions import Exit
from invocations.console import confirm
from fabric import Connection, task
from pathlib import Path
from scripts.testy_launch import get_launch_templates, get_snapshots, launch_from_distro, \
    launch_from_snapshot

testy = "\033[1;36mtesty\033[0m"
testy_config = ".testy"
wiredtiger = "\033[1;33mwiredtiger\033[0m"

# ---------------------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------------------

# Launch an AWS instance and install testy using the given WiredTiger and testy branches.
@task
def launch(c, distro, wiredtiger_branch="develop", testy_branch="main"):

    result = launch_from_distro(distro)
    if result['status'] != 0:
        print(f"Launch failed. {result['msg']}")
        return

    user = result['user']
    hostname = result['hostname']

    try:
        with Connection(f"{user}@{hostname}") as conn:
            install(conn, wiredtiger_branch, testy_branch)
    except Exception as e:
        print(f"The EC2 instance was launched successfully but the testy "
              f"installation failed: {e}")

    # Print summary on success.
    print("\n~~~~~~~~~~~~~~")
    print(f"Launch Summary")
    print("~~~~~~~~~~~~~~")
    print(f"The user is '{user}'")
    print(f"The host is '{hostname}'")
    print(f"The instance id is '{result['instance_id']}'")
    print(f"The instance name is '{result['instance_name']}'\n")

# Launch an AWS instance using a snapshot.
@task
def launch_snapshot(c, snapshot_id):

    result = launch_from_snapshot(snapshot_id)
    if result['status'] != 0:
        print(f"Launch failed. {result['msg']}")
        return

    user = result['user']
    hostname = result['hostname']

    # Print summary on success.
    print("\n~~~~~~~~~~~~~~")
    print(f"Launch Summary")
    print("~~~~~~~~~~~~~~")
    print(f"The user is '{user}'")
    print(f"The host is '{hostname}'")
    print(f"The instance id is '{result['instance_id']}'")
    print(f"The instance name is '{result['instance_name']}'\n")

# Install the testy framework.
@task
def install(c, wiredtiger_branch="develop", testy_branch="main"):

    # Get Linux distribution.
    result = c.run("cat /etc/*-release", hide=True)
    d = dict(line.split('=') for line in result.stdout.split('\n') if '=' in line)
    release = d["PRETTY_NAME"].strip('\"')
    print(f"Starting {testy} installation for {release} ...")

    # Read configuration file.
    config = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    config.read(testy_config)

    # Create application user.
    user = config.get("application", "user")
    create_user(c, user)

    # Create framework directories.
    testy_dir = config.get("application", "testy_dir")
    database_dir = config.get("application", "database_dir")
    service_script_dir = config.get("application", "service_script_dir")

    for dir in [testy_dir, database_dir, service_script_dir]:
        create_directory(c, dir)
    c.sudo(f"chown -R $(whoami):$(whoami) {testy_dir}")
    c.sudo(f"chown -R {user}:{user} {database_dir}")

    # Install prerequisite software.
    install_packages(c, release)

    # Add github to known_hosts.
    c.run("touch ~/.ssh/known_hosts && ssh-keygen -R github.com && " \
          "ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts", hide=True)

    # Clone repositories.
    for repo in [("testy", testy_branch), ("wiredtiger", wiredtiger_branch)]:
       git_clone(c, config.get(repo[0], "git_url"), config.get(repo[0], "home_dir"), repo[1])

    # Create working files and directories that can be modified by the framework user.
    create_working_copy(c, config.get("testy", "home_dir") + f"/{testy_config}",
              testy_dir, user)
    create_working_copy(c, config.get("testy", "workload_dir"), testy_dir, user)
    create_working_copy(c, config.get("testy", "service_script_dir"), testy_dir, user)

    # Build WiredTiger.
    wt_home_dir = config.get("wiredtiger", "home_dir")
    wt_build_dir = config.get("wiredtiger", "build_dir")
    if not build_wiredtiger(c, wt_home_dir, wt_build_dir, wiredtiger_branch):
        raise Exit(f"Failed to build {wiredtiger} for branch '{wiredtiger_branch}'.")

    # Install services.
    services = ["testy_service", "backup_service", "crash_service"]
    for service in services:
        install_service(c, config.get("testy", service))
    timers = ["backup_timer", "crash_timer"]
    for timer in timers:
        install_service_timer(c, config.get("testy", timer))

    # Print installation summary on success.
    print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print("The testy installation is complete!")
    print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print(f"The testy framework user is '{user}'")
    print(f"The testy framework directory is '{testy_dir}'")
    print(f"The testy workloads are found in '" +
          config.get("application", "workload_dir") + "'")
    print(f"The database directory is '{database_dir}'")
    print(f"The WiredTiger home directory is '{wt_home_dir}'")
    print(f"The WiredTiger build directory is '{wt_build_dir}'")

# Run the populate function as defined in the workload interface file.
@task
def populate(c, workload):

    current_workload = get_value(c, "application", "current_workload")
    service_name = Path(get_value(c, "testy", "testy_service")).name

    # Is testy running already?
    if current_workload:
        testy_service = get_service_instance_name(service_name, current_workload)
        if c.sudo(f"systemctl is-active {testy_service}", hide=True, warn=True):
            raise Exit(f"\n{testy} is running. Please stop {testy} to run populate.")

    # Verify the specified workload exists.
    wif = get_value(c, "application", "workload_dir") + f"/{workload}/{workload}.sh"
    if not c.run(f"test -f {wif}", warn=True):
        raise Exit(f"\nUnable to run populate: Workload '{workload}' not found.")

    # Run the populate workload.
    command = get_env(c, "environment") + " bash " + wif + " populate"

    if c.sudo(command, user=get_value(c, "application", "user"), warn=True):
        # Update the current workload.
        set_value(c, "application", "current_workload", workload)
        print(f"Populate succeeded for workload '{workload}'.")
    else:
        print(f"Populate failed for workload '{workload}'.")

# Start the framework using the specified workload. This function starts three services:
#   (1) testy-run executes the run function as defined in the workload interface file
#   (2) testy-backup
#   (3) testy-crash
@task
def start(c, workload, config_file=None):

    current_workload = get_value(c, "application", "current_workload")
    service_name = Path(get_value(c, "testy", "testy_service")).name
    skip_services = False

    # Is testy running already?
    if current_workload:
        testy_service = get_service_instance_name(service_name, current_workload)
        if c.sudo(f"systemctl is-active {testy_service}", hide=True, warn=True):
            raise Exit(f"\n{testy} is already running. Use 'fab restart' to " \
                        "change the workload.")
    elif not workload:
        raise Exit(f"Please specify a workload to run with 'fab -H <host> start <workload>.")

    # If we are running test/format we need to specify which config file to use.
    if workload == "test_format":
        if not config_file:
            print("Please specify a configuration file through 'fab -H <host> start test_format \
                  --config-file=<config>")
            print("To upload a config file, use fab -H <host> workload --format-config=<config>")
            return
        set_value(c, "application", "config_file", config_file)
        skip_services = True
    else:
        if config_file != None:
            raise Exit(f"Option --config-file is only specified fo test_format workloads.")

    # Verify the specified workload exists.
    wif = get_value(c, "application", "workload_dir") + f"/{workload}/{workload}.sh"
    if not c.run(f"test -f {wif}", warn=True):
        raise Exit(f"\nUnable to start {testy}: Workload '{workload}' not found.")

    # Enable service timers.
    if not skip_services:
        for timer in ["backup_timer", "crash_timer"]:
            timer_name = get_service_instance_name(
                Path(get_value(c, "testy", timer)).name, workload)
            if not c.sudo(f"systemctl enable {timer_name}", hide=True, warn=True):
                print(f"Failed to schedule ${timer_name} service timer.")

    # Update the environment variables for the shell scripts from .testy to systemd services 
    conf = get_systemd_service_conf(c, "environment")
    c.sudo(f"echo '{conf}' | sudo tee /etc/systemd/system/{service_name}.d/env.conf >/dev/null")
    c.sudo("systemctl daemon-reload")

    # Start the testy-run service which manages the long-running
    # workload and the start/stop behavior for the dependent testy-backup
    # service. The testy-backup service is started after the testy-run service
    # starts and is stopped when the testy-run service is stopped or fails.
    testy_service = get_service_instance_name(service_name, workload)
    c.sudo(f"systemctl start {testy_service}", user="root")
    if c.sudo(f"systemctl is-active {testy_service}", hide=True, warn=True):
        set_value(c, "application", "current_workload", workload)
        c.run(f"systemctl status {testy_service}")
        print(f"\nStarted {testy} running workload '{workload}'!")
    else:
        raise Exit(f"\nUnable to start {testy}.")

# Stop the testy framework, ensuring that all running processes complete gracefully
# and WiredTiger is shut down cleanly.
@task
def stop(c):

    skip_services = False
    workload = get_value(c, "application", "current_workload")
    if not workload:
        print(f"\nNothing to stop. No workload is defined.")
        return

    if workload == "test_format":
        skip_services = True
    
    if not skip_services:
        # Stop service timers for the workloads that have it running.
        stop_service_timer(c, workload)

    # Stop testy service.
    testy_service = get_service_instance_name(
        Path(get_value(c, "testy", "testy_service")).name, workload)

    if c.run(f"systemctl is-active {testy_service}", hide=True, warn=True):
        print(f"Stopping {testy}. Please wait ...")
        if c.sudo(f"systemctl stop {testy_service}", user="root"):
            print(f"{testy} stopped successfully.")
        else:
            print(f"Failed to stop {testy}.")
    else:
        print(f"{testy} is not running.")

    if not skip_services:
        # Disable the crash and backup services.
        disable_crash_backup_services(c, workload)

# Restarts with the specified workload. If no workload is specified, take the current workload. 
@task
def restart(c, workload=None, validate=False):

    # If there is no current workload and no specified workload, return.
    current_workload = get_value(c, "application", "current_workload")
    if not current_workload and not workload:
        print(f"No workload is defined. Please specify a workload.")
        return

    # If no workload is specified, take the current workload. 
    if not workload:
        workload = current_workload
        
    # Stop the testy workload.
    stop(c)

    # Validate the stopped workload, if any.
    if validate:
        if current_workload:
        # FIXME-WTBUILD-108
            print("Validation skipped, see WTBUILD-108.")
        #     user = get_value(c, "application", "user")
        #     wif = get_value(c, "application", "workload_dir") + f"/{current_workload}/{current_workload}.sh"
        #     command = wif + " validate"
        #     result = c.sudo(command, user=user, warn=True)
        #     if not result:
        #         raise Exit(f"Validate failed for '{current_workload}' workload.")
        else:
            print("Validation skipped, no workload was previously defined.")

    # Restart the testy workload.    
    start(c, workload)

# Update the WiredTiger and/or testy source on the remote server to the specified GitHub
# branch. If an argument is not specified, no update is made. Updates to WiredTiger are
# performed in line with the WiredTiger documentation for upgrading and downgrading databases,
# as specified here: https://source.wiredtiger.com/develop/upgrade.html.
@task
def update(c, wiredtiger_branch=None, testy_branch=None):

    if not wiredtiger_branch and not testy_branch:
        raise Exit("\nError: No update target specified.")

    # Stop testy service.
    stop(c)

    # Save values set by the application.
    workload = get_value(c, "application", "current_workload")

    # Do the updates.
    update_success = True

    if testy_branch:
        try:
            update_testy(c, testy_branch)
        except:
            print(f"\nFailed to update {testy} to branch '{testy_branch}'.")
            update_success = False
        finally:
            # The update_testy function may fail after updating the remote configuration
            # file. Make sure the pre-update configuration values are restored on both
            # failure and success.
            if workload:
                set_value(c, "application", "current_workload", workload)

    if wiredtiger_branch:
        try:
            update_wiredtiger(c, wiredtiger_branch)
        except:
            print(f"\nFailed to update {wiredtiger} to branch '{wiredtiger_branch}'.")
            update_success = False

    if update_success:
        # Start testy service.
        start(c, workload)
    else:
        raise Exit("One or more errors occurred during update. Please retry the " \
                   f"update or run 'fab start' to restart {testy}.")

# The workload function takes three optional arguments: upload, upload_config and describe. 
# If no arguments are provided, the current workload is returned.
@task
def workload(c, upload=None, describe=None, upload_config=None):
    """ Upload and describe workloads.
    Up to three optional arguments can be taken at a time. If more than one option is specified at
    once, they will be executed in the following order (regardless of order they are called):
       1. upload
       2. describe
       3. upload_config
    If an option fails at any point, it will print an error message, exit the current option and 
    continue running the following options.  
    """
    current_workload = get_value(c, "application", "current_workload")
    user = get_value(c, "application", "user")
    dest = get_value(c, "application", "workload_dir")

    # Uploads a workload from a local directory to the testy server. Upload takes the absolute or
    # relative  of the archive. After it is uploaded to the server, the archive gets unpacked in 
    # the workloads directory. The workload should be in a directory named after the workload, with 
    # a shell script of the same workload name. 
    if upload:
        workload_name = Path(upload).stem.split('.')[0]
        archived_name = os.path.basename(upload)
        src = f"{dest}/{archived_name}"
        exists = overwrite = False

        if c.run(f"[ -d {dest}/{workload_name} ] ", warn=True):
            exists = True
            overwrite = confirm(f"Workload '{workload_name}' already exists. Would you like to " \
                + "overwrite it?", assume_yes=False)
            if not overwrite:
                print(f"The workload '{workload_name}' has not been uploaded. ")
        
        if exists == overwrite:
            script = get_value(c, "testy", "unpack_script")
            try: 
                c.put(upload, "/tmp/", preserve_mode=True)
            except Exception as e:
                print(e)
                print(f"Upload failed for workload '{workload_name}'.")
            else:
                c.sudo(f"rm -rf {dest}/{workload_name}")
                copy = c.sudo(f"cp /tmp/{archived_name} {src}", user=user, warn=True)
                unpack = c.sudo(f"python3 {script} unpack_archive {src} {dest}", user=user, \
                    warn=True)
                if copy and unpack: 
                    print(f"Upload succeeded! Workload '{workload_name}' ready for use.")
                else:
                    print(f"Failed to add '{workload_name}'.")
                c.sudo(f"rm -f {src} /tmp/{archived_name}")

    # Describes the specified workload by running the describe function as defined in the workload
    # interface file. A workload must be specified for the describe option. 
    if describe:
        wif = f"{dest}/{describe}/{describe}.sh"
        command = wif + " describe"
        result = c.sudo(command, user=user, warn=True)
        if not result: 
            print(f"Unable to describe '{describe}' workload.")
        elif result.stdout == "":
            print(f"No description provided for workload '{describe}'.")
    
    # Upload a test format config file to the test_format workloads directory ready for use, this 
    # function takes both relative or absolute paths to your local config file. 
    if upload_config:
        config_filename = os.path.basename(upload_config)
        src = f"{dest}/test_format/{config_filename}"

        try:
            c.put(upload_config, f"/tmp/", preserve_mode=True)
        except Exception as e:
            print(e)
            print(f"Upload failed for config file '{config_filename}'.")
        else:
            if c.sudo(f"cp -f /tmp/{config_filename} {src}", user=user, warn=True):
                print(f"Upload succeeded for config file '{config_filename}'.")
            c.sudo(f"rm -f /tmp/{config_filename}")

    
    # If no option has been specified, print the current workload and return as usual.  
    if not describe and not upload and not upload_config:
        if current_workload:
            print(f"The current workload is {current_workload}.")
        else: 
            print("The current workload is unspecified.")
    
    return current_workload

# The function will take a specified snapshot ID or a list of snapshot IDs separated by a comma with
# no spaces, and delete the corresponding snapshots.
@task
def snapshot_delete(c, snapshot_id=None):
    if not snapshot_id:
        print("Please specify the snapshot(s) you wish to delete through \
              --snapshot_id=<snapshotid,snapshotid1> separated by a ',' .")
        return
    
    snapshot_ids = snapshot_id.split(",")
    for snapshot_id in snapshot_ids:
        result = c.run(f"aws ec2 delete-snapshot \
        --snapshot-id {snapshot_id}")
        if result.stderr:
            raise Exit(result.stderr)
        print(f"Deleted snapshot '{snapshot_id}'.")       

# The list function takes three optional arguments: distros, snapshots and workloads.
#    --distros    List the available distributions for launching a testy server.
#    --snapshots  List the snapshots created from scheduled backups, validation failure,
#                 and wiredtiger failure.
#    --workloads  List the workloads available on the specified testy server. The -H
#                 option is required.
@task
def list(c, distros=False, snapshots=False, workloads=False):
    if distros:
        launch_templates = None
        try:
            launch_templates = get_launch_templates()
        except Exception as e:
            print(f"Error: {str(e)}")
        else:
            print("\n\033[1mAvailable distros: \033[0m")
            if launch_templates:
                for template in launch_templates:
                    print(f"{template}")
            else:
                print("No launch templates found.")

    if snapshots:
        snapshots = None
        try:
            snapshots = get_snapshots()
        except Exception as e:
            print(f"Error: {str(e)}")
        else:
            print("\n\033[1mAvailable snapshots: \033[0m")
            if snapshots:
                for snapshot in snapshots:
                    print(f"{snapshot}")
            else:
                print("No snapshots found.")

    if workloads:
        # The -H option is mandatory to list the workloads.
        if type(c) is not Connection:
            print("Please specify the testy server with the -H option to list the workloads.")
            return

        current_workload = get_value(c, "application", "current_workload")
        user = get_value(c, "application", "user")
        command = "ls " + get_value(c, "application", "workload_dir")

        result = c.sudo(command, user=user, warn=True, hide=True)
        if result.ok:
            print("\n\033[1mAvailable workloads: \033[0m")
            if current_workload:
                result.stdout = re.sub(r"(?<!-)\b%s(?!-)\b" % current_workload, \
                    f"\033[1;35m{current_workload} (active)\033[0m", result.stdout)
            print(result.stdout)
        else:
            print(result.stderr)

    if not workloads:
        print()

# Print information about the testy framework including testy and WiredTiger branch and commit hash,
# current workload, testy service status and the WiredTiger version. 
@task
def info(c):
    wt_dir = get_value(c, "wiredtiger", "home_dir")
    with c.cd(wt_dir):
        wt_branch = c.run("git rev-parse --abbrev-ref HEAD", hide=True)
        wt_commit = c.run("git rev-parse HEAD", hide=True)
        wt_version = c.run(". RELEASE_INFO && echo $WIREDTIGER_VERSION", hide=True)

    testy_dir = get_value(c, "testy", "home_dir")
    with c.cd(testy_dir):
        testy_branch = c.run("git rev-parse --abbrev-ref HEAD", hide=True)
        testy_commit = c.run("git rev-parse HEAD", hide=True)

    testy_workload = None
    with open(os.devnull, "w") as f, redirect_stdout(f):
        testy_workload = workload(c)

    testy_service = get_service_instance_name(
        Path(get_value(c, "testy", "testy_service")).name, testy_workload)
    testy_status = c.run(f"systemctl is-active {testy_service}", hide=True, warn=True)

    print(f"{wiredtiger} branch:  {wt_branch.stdout}"
          f"{wiredtiger} commit:  {wt_commit.stdout}"
          f"{wiredtiger} version: {wt_version.stdout}\n"
          f"{testy} branch:   {testy_branch.stdout}"
          f"{testy} commit:   {testy_commit.stdout}"
          f"{testy} workload: {testy_workload}\n"
          f"{testy} status:   {testy_status.stdout}")

    if testy_status:
        c.run(f"systemctl status {testy_service}")

# ---------------------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------------------

# Return the systemd service name for the specified service template and instance.
def get_service_instance_name(service_name, instance_name):

    return service_name.replace("@", f"\@{instance_name}")

# Return the value corresponding to the specified key from the specified section
# of the remote testy configuration file.
def get_value(c, section, key):

    return parser_operation(c, "get_value", section, key)

# Return the key/value pairs in the specified section of the testy configuration file
# as a single string of shell environment values.
def get_env(c, section):

    return parser_operation(c, "get_env", section)

# Return a string suitable for generating a drop-in .conf file of environment
# values for the testy systemd services.
def get_systemd_service_conf(c, section):

    return parser_operation(c, "get_systemd_service_conf", section)

# Set the value corresponding to the specified key from the specified section
# of the testy configuration file.
def set_value(c, section, key, value):

    return parser_operation(c, "set_value", section, key, value)

# Call the specified parsing function on the remote host.
def parser_operation(c, func, section, key=None, value=None):

    parser = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    parser.read(testy_config)

    config = parser.get("application", "testy_dir") + f"/{testy_config}"
    script = parser.get("testy", "parse_script")
    user = parser.get("application", "user")

    if key:
        if value:
            command = f"python3 {script} {func} {config} {section} {key} {value}"
        else:
            command = f"python3 {script} {func} {config} {section} {key}"
    else:
        command = f"python3 {script} {func} {config} {section}"

    result = c.sudo(command, user=user, warn=True, hide=True)
    if result:
        return result.stdout
    else:
        raise Exit(f"Error: {result.stderr}")
    
# Stop the service timer
def stop_service_timer(c, workload):
    # Stop service timers.
    for timer in ["backup_timer", "crash_timer"]:
        timer_name = get_service_instance_name(
            Path(get_value(c, "testy", timer)).name, workload)
        c.sudo(f"systemctl stop {timer_name}", user="root")

    # Check if services are still in progress.
    service_name = get_service_instance_name(
        Path(get_value(c, "testy", "backup_service")).name, workload)
    if c.run(f"systemctl is-active {service_name}", hide=True, warn=True):
        print("A backup is currently in progress. The service will terminate when the " \
            "backup completes.")
    service_name = get_service_instance_name(
        Path(get_value(c, "testy", "crash_service")).name, workload)
    result = c.run(
        f"systemctl show --property MainPID {service_name} | awk -F '=' '{{print $2}}'",
        hide=True)
    if result.stdout.strip() != "0":
        print("A crash test is currently in progress. The service will terminate when " \
            "the crash test completes.")

# Disable the crash and backup services for the current workload.
def disable_crash_backup_services(c, workload):
    # Disable service timers for the current workload.
    timer_name = get_service_instance_name(
        Path(get_value(c, "testy", "backup_timer")).name, workload)
    if c.sudo(f"systemctl disable {timer_name}", hide=True, warn=True):
        print(f"Backup scheduling is disabled.")
    timer_name = get_service_instance_name(
        Path(get_value(c, "testy", "crash_timer")).name, workload)
    if c.sudo(f"systemctl disable {timer_name}", hide=True, warn=True):
        print(f"Crash test scheduling is disabled.")

# Create framework superuser account.
def create_user(c, username):

    # Add user.
    if c.run(f"id -u {username}", warn=True, hide=True).failed:
        c.sudo(f"useradd {username}")
        print(f"Created user '{username}'")
    else:
        print(f"Found existing user '{username}'")

    # Grant sudo privileges.
    if c.run("getent group sudo", warn=True, hide=True):
        c.sudo(f"usermod -aG sudo,adm {username}", warn=True)
    elif c.run("getent group wheel", warn=True, hide=True):
        c.sudo(f"usermod -aG wheel,adm {username}", warn=True)
    c.sudo(f"echo '{username} ALL=(ALL:ALL) NOPASSWD:ALL' | " \
           f"sudo tee /etc/sudoers.d/{username}-user >/dev/null", user="root")

    result = c.sudo("groups", user=username, hide=True)
    print(f"Groups for user '{username}' are (" + result.stdout.strip() + ")")

# Create framework directories.
def create_directory(c, dir):

    print(f"Creating directory '{dir}' ... ", end='', flush=True)
    if c.sudo(f"test -d {dir}", warn=True):
        print(f"directory exists")
    else:
        if c.sudo(f"mkdir -p {dir}", warn=True).failed:
            raise Exit(f"\nError: Unable to create directory '{dir}'")
        print("done!")

# Clone git repository.
def git_clone(c, git_url, local_dir, branch):

    repo = Path(git_url).stem
    if c.run(f"test -d {local_dir}", warn=True):
        print(f"Directory '{local_dir}' exists. " \
              f"Repository '{repo}' will not be cloned.")
    else:
        print(f"Cloning branch '{branch}' of '{repo}' repository ...")
        if c.run(f"git clone --branch {branch} {git_url} {local_dir}", warn=True):
            print("Success!")
        else:
            raise Exit()

# Check out the specified branch from GitHub.
def git_checkout(c, dir, branch):
    with c.cd(dir):
        print(f"Checking out branch '{branch}' ...")
        if c.run(f"git fetch && git checkout {branch} && git pull", warn=True):
            return True
        return False

# Create a working copy of a file or directory on the remote machine that can
# be modified by the specified user.
#   'src' is the full path of the file or directory to copy
#   'dest' is the full path of the directory to copy into
def create_working_copy(c, src, dest, user=None):

    print(f"Copying '{src}' to '{dest}' ... ", end='', flush=True)
    result = c.sudo(f"cp -r {src} {dest}", warn=True, hide=True)
    if result:
        print("done!")
    else:
        raise Exit(f"failed\n{result.stderr}")
    if user:
        dest_name = f"{dest}/" + Path(src).name
        print(f"Updating user to '{user}' for '{dest_name}'")
        c.sudo(f"chown -R {user}:{user} {dest_name}")

# Build WiredTiger for the specified branch. The function returns True if the WiredTiger
# configuration and build succeed and False if any of the steps fail. An error message is
# printed to stderr if the command executed by the Fabric run function returns a non-zero
# status.
def build_wiredtiger(c, home_dir, build_dir, branch):

    with c.cd(home_dir):
        try:
            c.run(f"rm -rf {build_dir} && mkdir {build_dir}")
        except:
            return False

    with c.cd(build_dir):
        try:
            ninja_build = c.run("which ninja", warn=True, hide=True)

            print(f"Configuring {wiredtiger} for branch '{branch}'...")
            c.run("cmake ../. -G Ninja") if ninja_build else c.run("cmake ../.")
            print("-- Configuration complete!")

            print(f"Building {wiredtiger} for branch '{branch}' ...")
            if ninja_build:
                c.run("ninja -j $(grep -c ^processor /proc/cpuinfo)")
            else:
                c.run("make -j $(grep -c ^processor /proc/cpuinfo)")
            print("-- Build complete!")
        except:
            return False

    return True

# Install prerequisite software packages.
def install_packages(c, release):

    if c.run("which apt", warn=True, hide=True):
        installer = "apt"
    elif c.run("which apt-get", warn=True, hide=True):
        installer = "apt-get"
    elif c.run("which dnf", warn=True, hide=True):
        installer = "dnf"
    elif c.run("which yum", warn=True, hide=True):
        installer = "yum"
    else:
        raise Exit("Error: Unable to determine package installer.")

    print("Installing required software packages ...", flush=True)

    if release.startswith("Amazon Linux 2"):
        c.sudo(f"{installer} -y update", warn=True, hide=True)
        packages = ["gcc10", "gcc10-c++", "git", "libarchive", "python3-devel", "swig",
                    "unzip"]
        for package in packages:
            if c.run(f"{installer} list installed {package}", warn=True, hide=True):
                print(f" -- Package '{package}' is already the newest version.", flush=True)
                continue
            if c.sudo(f"{installer} -y install {package}", warn=True, hide=True):
                print(f" -- Package '{package}' installed by {installer}.", flush=True)
        for gcc in ["x86_64-redhat-linux-gcc10", "aarch64-redhat-linux-gcc10"]:
            if c.run(f"ls /usr/bin/{gcc}-gcc", warn=True, hide=True):
                c.sudo(f"alternatives --install /usr/bin/gcc gcc /usr/bin/{gcc}-gcc 20 \
                         --slave /usr/bin/ar ar /usr/bin/gcc10-ar \
                         --slave /usr/bin/ld ld /usr/bin/gcc10-ld")
                c.sudo(f"alternatives --install /usr/bin/g++ g++ /usr/bin/{gcc}-g++ 20")
                break

        for package in ["pip", "cmake", "ninja"]:
            if c.sudo(f"python3 -m pip install {package} --upgrade", warn=True, hide=True):
                print(f" -- Package '{package}' installed by pip.", flush=True)

        install_bash(c)

    elif release.startswith("Ubuntu 20") or release.startswith("Ubuntu 22"):
        packages = ["cmake", "ccache", "gcc", "g++", "git", "ninja-build", "python3-dev", "swig",
                    "unzip"]
        c.sudo(f"{installer} update", warn=True, hide=True)
        for package in packages:
            if c.run(f"dpkg -s {package}", warn=True, hide=True):
                print(f" -- Package '{package}' is already the newest version.", flush=True)
                continue
            if c.sudo(f"{installer} -y install {package}", warn=True, hide=True):
                print(f" -- Package '{package}' installed by {installer}.", flush=True)

    elif release.startswith("Ubuntu 18"):
        c.sudo("add-apt-repository ppa:ubuntu-toolchain-r/test", hide=True)
        packages = ["cmake", "ccache", "gcc-11", "g++-11", "git", "ninja-build",
                    "python3-dev", "swig", "unzip"]
        c.sudo(f"{installer} update", warn=True, hide=True)
        for package in packages:
            if c.run(f"dpkg -s {package}", warn=True, hide=True):
                print(f" -- Package '{package}' is already the newest version.", flush=True)
                continue
            if c.sudo(f"{installer} -y install {package}", warn=True, hide=True):
                print(f" -- Package '{package}' installed by {installer}.", flush=True)
        c.sudo("update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 20")
        c.sudo("update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-11 20")

    else:
        raise Exit(f"Package installation is not implemented for {release}.")

    install_aws_cli(c)
    print("Package installation complete!")

# Install the latest AWS CLI.
def install_aws_cli(c):
    result=c.run("aws --version", warn=True, hide=True)
    if result and result.stdout.startswith("aws-cli/2"):
        print(" -- Package 'aws' is already compatible.", flush=True)
        return

    aws_cli="awscli-exe-linux-x86_64"
    result=c.run("uname -m", warn=True, hide=True)
    if result and (result.stdout.startswith("aarch") or result.stdout.startswith("arm")):
        aws_cli="awscli-exe-linux-aarch64"

    c.run(f"curl https://awscli.amazonaws.com/{aws_cli}.zip -o /tmp/{aws_cli}.zip",
        warn=True, hide=True)
    c.run(f"unzip -o /tmp/{aws_cli}.zip -d /tmp/{aws_cli}", warn=True, hide=True)
    c.sudo(f"/tmp/{aws_cli}/aws/install", warn=True, hide=True)
    c.run(f"rm -rf /tmp/{aws_cli}")
    c.run(f"rm -rf /tmp/{aws_cli}.zip")
    print(" -- Package 'aws' installed.", flush=True)

def install_bash(c):
    result=c.run("/bin/bash --version | head -1 | cut -d ' ' -f4", warn=True, hide=True)
    if result and int(result.stdout[0]) >= 5:
        print(" -- Package 'bash' is already compatible.", flush=True)
        return

    bash_install="bash-5.1.16"

    with c.cd("/tmp"):
        c.run(f"curl -O http://ftp.gnu.org/gnu/bash/{bash_install}.tar.gz", warn=True, hide=True)
        c.run(f"tar xvf {bash_install}.tar.gz", warn=True, hide=True)
    with c.cd(f"/tmp/{bash_install}"):
        c.run("./configure --prefix=/usr && make", warn=True, hide=True)
        c.run("sudo make install", hide=True)
    c.run(f"rm -rf /tmp/{bash_install}")
    c.run(f"rm -rf /tmp/{bash_install}.tar.gz")

    print(" -- Package 'bash' installed.", flush=True)

# Install a systemd service.
def install_service(c, service):

    service_name = Path(service).name
    print(f"Installing service '{service_name}' ... ", end='', flush=True)
    if not c.run(f"test -f {service}", warn=True):
        print("failed")
        raise Exit(f"-- Unable to install '{service}': File not found.")
    else:
        conf_dir = f"/etc/systemd/system/{service_name}.d"
        c.sudo(f"mkdir -p {conf_dir}")
        conf = get_systemd_service_conf(c, "environment")
        c.sudo(f"echo '{conf}' | sudo tee {conf_dir}/env.conf >/dev/null")
        c.sudo(f"cp {service} /etc/systemd/system")
        c.sudo("systemctl daemon-reload")
        print("done!")

# Install a systemd timer.
def install_service_timer(c, service_timer):

    service_timer_name = Path(service_timer).name
    print(f"Installing service timer '{service_timer_name}' ... ", end='', flush=True)
    if not c.run(f"test -f {service_timer}", warn=True):
        print("failed")
        raise Exit(f"-- Unable to install '{service_timer}': File not found.")
    else:
        c.sudo(f"cp {service_timer} /etc/systemd/system")
        print("done!")

# Update the wiredtiger code on the remote machine to the specified branch, configure,
# and build. If any of these steps fail, attempt to restore the previous branch.
def update_wiredtiger(c, branch):

    # Get current branch.
    wt_home_dir = get_value(c, "wiredtiger", "home_dir")
    old_branch = None
    with c.cd(wt_home_dir):
        result = c.run("git rev-parse --abbrev-ref HEAD", hide=True)
        if not result.stdout:
            raise Exit(f"Error: {wiredtiger} is not currently on a branch.")
        old_branch = result.stdout.strip()
        commit = c.run("git rev-parse HEAD", hide=True)
        commit_hash = commit.stdout.strip()

    # Check out branch from GitHub.
    if not git_checkout(c, wt_home_dir, branch):
        raise Exit(f"Failed to update {wiredtiger} to branch '{branch}'.")

    # Build wiredtiger.
    wt_build_dir = get_value(c, "wiredtiger", "build_dir")
    if not build_wiredtiger(c, wt_home_dir, wt_build_dir, branch):
        print(f"Failed to build {wiredtiger} for branch '{branch}'.")
        # Try restoring to previous branch.
        print(f"\nAttempting to restore branch '{old_branch}' ...")
        # If we are on the same branch and the new commits breaks, use an older working commit.
        if old_branch == branch:
            if git_checkout(c, wt_home_dir, commit_hash) and \
            build_wiredtiger(c, wt_home_dir, wt_build_dir, commit_hash):
                print(f"Restored {wiredtiger} branch '{branch}' to the previous commit.")
        elif git_checkout(c, wt_home_dir, old_branch) and \
           build_wiredtiger(c, wt_home_dir, wt_build_dir, old_branch):
            print(f"Restored {wiredtiger} to branch '{branch}'.")
        else:
            raise Exit(f"\nFailed to restore {wiredtiger} to previous branch '{old_branch}'.")
    else:
        print(f"\nSuccessfully updated {wiredtiger} to branch '{branch}'.\n")

# Update the testy code on the remote machine to the specified branch. Update the
# working copy of the .testy configuration, preserving any values set by the
# framework, and update the available workloads.
def update_testy(c, branch):

    # Check out branch from GitHub.
    testy_git_dir = get_value(c, "testy", "home_dir")
    if not git_checkout(c, testy_git_dir, branch):
        raise Exit(f"Failed to update {testy} to branch '{branch}'.")

    # Copy testy config and workload directory.
    user = get_value(c, "application", "user")
    create_working_copy(c, f"{testy_git_dir}/{testy_config}",
                        get_value(c, "application", "testy_dir"), user)
    create_working_copy(c, get_value(c, "testy", "workload_dir") + "/*",
                        get_value(c, "application", "workload_dir"), user)
    create_working_copy(c, get_value(c, "testy", "service_script_dir") + "/*",
                        get_value(c, "application", "service_script_dir"), user)

    # Update services.
    services = ["testy_service", "backup_service", "crash_service"]
    for service in services:
        install_service(c, get_value(c, "testy", service))
    timers = ["backup_timer", "crash_timer"]
    for timer in timers:
        install_service_timer(c, get_value(c, "testy", timer))

    print(f"\nSuccessfully updated {testy} to branch '{branch}'.\n")
