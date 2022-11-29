# fabfile.py
# Remote management commands for testy: A WiredTiger 24/7 workload testing framework.

import re, configparser as cp
from fabric import task
from pathlib import Path
from invoke.exceptions import Exit
from invocations.console import confirm

testy_config = ".testy"
testy = "\033[1;36mtesty\033[0m"
wiredtiger = "\033[1;33mwiredtiger\033[0m"


# ---------------------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------------------

# Install the testy framework.
@task
def install(c, wiredtiger_branch="develop", testy_branch="main"):

    # Read configuration file.
    config = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    config.read(testy_config)

    # Create application user.
    user = config.get("application", "user")
    create_user(c, user)

    # Create framework directories.
    testy_dir = config.get("application", "testy_dir")
    backup_dir = config.get("application", "backup_dir")
    database_dir = config.get("application", "database_dir")

    for dir in [testy_dir, backup_dir, database_dir]:
        create_directory(c, dir)
    c.sudo(f"chown -R $(whoami):$(whoami) {testy_dir}")
    c.sudo(f"chown -R {user}:{user} {database_dir}")

    # Install prerequisite software.
    install_packages(c)

    # Clone repositories.
    for repo in [("testy", testy_branch), ("wiredtiger", wiredtiger_branch)]:
       git_clone(c, config.get(repo[0], "git_url"), config.get(repo[0], "home_dir"), repo[1])

    # Create working files and directories that can be modified by the framework user.
    create_working_copy(c, config.get("testy", "home_dir") + f"/{testy_config}",
              testy_dir, user)
    create_working_copy(c, config.get("testy", "workload_dir"), testy_dir, user)

    # Build WiredTiger.
    wt_home_dir = config.get("wiredtiger", "home_dir")
    wt_build_dir = config.get("wiredtiger", "build_dir")
    if not build_wiredtiger(c, wt_home_dir, wt_build_dir, wiredtiger_branch):
        raise Exit(f"Failed to build {wiredtiger} for branch '{wiredtiger_branch}'.")

    # Install services.
    # TODO: Update this part of the installation when the service implementation
    #       is complete, and add properties in .testy for the service filenames.
    install_service(c, config.get("testy", "testy_service"))
    #install_service(c, config.get("testy", "backup_service"))
    #install_service(c, config.get("testy", "crash_service"))

    # Print installation summary on success.
    print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print("The testy installation is complete!")
    print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print(f"The testy framework user is '{user}'")
    print(f"The testy framework directory is '{testy_dir}'")
    print(f"The testy workloads are found in '" +
          config.get("application", "workload_dir") + "'")
    print(f"The database directory is '{database_dir}'")
    print(f"The database backup directory is '{backup_dir}'")
    print(f"The WiredTiger home directory is '{wt_home_dir}'")
    print(f"The WiredTiger build directory is '{wt_build_dir}'")

# Run the populate function as defined in the workload interface file.
@task
def populate(c, workload):

    current_workload = get_value(c, "application", "current_workload")
    service_name = Path(get_value(c, "testy", "testy_service")).name

    # Is testy running already?
    if current_workload:
        service = f"$(systemd-escape --template {service_name} \"{current_workload}\")"
        if c.sudo(f"systemctl is-active {service}", hide=True, warn=True):
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
        print(f"populate succeeded for workload '{workload}'")
    else:
        print(f"populate failed for workload '{workload}'")

# Start the framework using the specified workload. This function starts three services:
#   (1) testy-run executes the run function as defined in the workload interface file
#   (2) testy-backup
#   (3) testy-crash
@task
def start(c, workload):

    current_workload = get_value(c, "application", "current_workload")
    service_name = Path(get_value(c, "testy", "testy_service")).name

    # Is testy running already?
    if current_workload:
        service = f"$(systemd-escape --template {service_name} \"{current_workload}\")"
        if c.sudo(f"systemctl is-active {service}", hide=True, warn=True):
            raise Exit(f"\n{testy} is already running. Use 'fab restart' to " \
                        "change the workload.")

    # Verify the specified workload exists.
    wif = get_value(c, "application", "workload_dir") + f"/{workload}/{workload}.sh"
    if not c.run(f"test -f {wif}", warn=True):
        raise Exit(f"\nUnable to start {testy}: Workload '{workload}' not found.")

    # First start the testy-run service which controls the long-running workload.
    service = f"$(systemd-escape --template {service_name} \"{workload}\")"
    c.sudo(f"systemctl start {service}", user="root")
    if c.sudo(f"systemctl is-active {service}", hide=True, warn=True):
        set_value(c, "application", "current_workload", workload)
        c.run(f"systemctl status {service}")
        print(f"\nStarted {testy} running workload '{workload}'!")
    else:
        raise Exit("\nUnable to start {testy}.")

    # Then start the backup and crash trigger services (OR start them as part of the
    # testy-run service).
    # TODO: Update the start function when the service implementations are complete

# Stop the testy framework, ensuring that all running processes complete gracefully
# and WiredTiger is shut down cleanly.
@task
def stop(c):

    # TODO: Update this function as necessary when the backup and crash trigger
    # services are implemented.

    workload = get_value(c, "application", "current_workload")
    if not workload:
        print(f"\nUnable to stop {testy}: No workload is defined.")

    service_name = Path(get_value(c, "testy", "testy_service")).name
    service = f"$(systemd-escape --template {service_name} \"{workload}\")"

    if c.run(f"systemctl is-active {service}", hide=True, warn=True):
        print(f"Stopping {testy}. Please wait ...")
        if c.sudo(f"systemctl stop {service}", user="root"):
            print(f"{testy} stopped successfully.")
        else:
            raise Exit(f"Failed to stop {testy}.")
    else:
        print(f"{testy} is not running.")

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
            # Restore configuration values.
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

# The workload function takes 3 optional arguments upload, list, describe. If no arguments are 
# provided, the current workload is returned.
@task
def workload(c, upload=None, list=False, describe=None):
    """ Upload, list, and describe workloads. 
    Up to three optional arguments can be taken at a time. If more than one option is specified at
    once, they will be executed in the following order (regardless of order they are called): - 
       1. upload
       2. list
       3. describe
    If an option fails at any point, it will print an error message, exit the current option and 
    continue running the following options.  
    """
    current_workload = get_value(c, "application", "current_workload")
    user = get_value(c, "application", "user")

    # Uploads a workload from a local directory to the testy server. Upload takes the full path of 
    # the archive, including the archive name. After it is uploaded to the server, the archive gets
    # unpacked in the workloads directory. 
    if upload:
        dest = get_value(c, "application", "workload_dir")
        src = f"{dest}/{upload}"
        workload_name = Path(src).stem.split('.')[0]
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
                c.put(upload, "/tmp", preserve_mode=True)
            except Exception as e:
                print(e)
                print(f"Upload failed for workload '{workload_name}'.")
            else:
                copy = c.sudo(f"cp /tmp/{upload} {src}", user=user, warn=True)
                unpack = c.sudo(f"python3 {script} unpack_archive {src} {dest}", user=user, \
                    warn=True)
                if copy and unpack: 
                    print(f"Upload succeeded! Workload '{workload_name}' ready for use.")
                else:
                    print(f"Failed to add '{workload_name}'.")
                c.sudo(f"rm -f {src} /tmp/{upload}")

    # Lists the available workloads in the workloads directory and highlights the current workload.
    if list:
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

    # Describes the specified workload by running the describe function as defined in the workload
    # interface file. A workload must be specified for the describe option. 
    if describe:
        wif = get_value(c, "application", "workload_dir") + f"/{describe}/{describe}.sh"
        command = wif + " describe"
        result = c.sudo(command, user=user, warn=True)
        if not result: 
            print(f"Unable to describe '{describe}' workload.")
        elif result.stdout == "":
            print(f"No description provided for workload '{describe}'.")
    
    # If no option has been specified, print the current workload and return as usual.  
    if not describe and not upload and not list:
        if current_workload:
            print(f"The current workload is {current_workload}.")
        else: 
            print("The current workload is unspecified.")


# ---------------------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------------------

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
        return c.run(f"git checkout {branch}", warn=True)

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
            c.run("git pull")
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

# Install prerequisite software.
def install_packages(c):

    if c.run("which apt", warn=True, hide=True):
        installer = "apt"
    elif c.run("which dnf", warn=True, hide=True):
        installer = "dnf"
    elif c.run("which yum", warn=True, hide=True):
        installer = "yum"
    else:
        raise Exit("Error: Unable to determine package installer.")

    is_rpm = (installer != "apt")
    packages = ["cmake", "ccache", "ninja-build", "python3-dev", "swig", "libarchive"]
    print("Installing required software packages")

    if is_rpm:
        for package in packages:
            if c.run(f"{installer} list installed {package}", warn=True, hide=True):
                print(f"-- Package '{package}' is already installed.")
            elif c.sudo(f"{installer} -y install {package}", warn=True, hide=True):
                print(f"-- Installed package '{package}'.")
    else:
        for package in packages:
            if c.run(f"dpkg -s {package}", warn=True, hide=True):
                print(f"-- Package '{package}' is already installed.")
            elif c.sudo(f"{installer} -y install {package}", warn=True, hide=True):
                print(f"-- Installed package '{package}'.")

    # Attempt to pip install ninja if it was not available through the package manager.
    if not c.run("which ninja", warn=True, hide=True):
        if c.sudo(f"python3 -m pip install ninja", warn=True, hide=True):
            print(f"-- Installed package 'ninja'.")

    print("-- Package installation complete!")

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
        c.sudo(f"cp {service} /etc/systemd/system && sudo systemctl daemon-reload")
        print("done!")

# Update the wiredtiger code on the remote machine to the specified branch, configure,
# and build. If any of these steps fail, attempt to restore the previous branch.
def update_wiredtiger(c, branch):

    # Get current branch.
    wt_home_dir = get_value(c, "wiredtiger", "home_dir")
    old_branch = None
    with c.cd(wt_home_dir):
        result = c.run("git branch --show-current", hide=True)
        if not result.stdout:
            raise Exit(f"Error: {wiredtiger} is not currently on a branch.")
        old_branch = result.stdout.strip()

    # Check out branch from GitHub.
    if not git_checkout(c, wt_home_dir, branch):
        raise Exit(f"Failed to update {wiredtiger} to branch '{branch}'.")

    # Build wiredtiger.
    wt_build_dir = get_value(c, "wiredtiger", "build_dir")
    if not build_wiredtiger(c, wt_home_dir, wt_build_dir, branch):
        print(f"Failed to build {wiredtiger} for branch '{branch}'.")
        # Try restoring to previous branch.
        print(f"\nAttempting to restore branch '{old_branch}' ...")
        if git_checkout(c, wt_home_dir, old_branch) and \
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

    # Update services.
    install_service(c, get_value(c, "testy", "testy_service"))
    #install_service(c, get_value(c, "testy", "backup_service"))
    #install_service(c, get_value(c, "testy", "crash_service"))

    print(f"\nSuccessfully updated {testy} to branch '{branch}'.\n")
