# fabfile.py
# Remote management commands for testy: A WiredTiger 24/7 workload testing framework.

import configparser as cp
from fabric import task
from pathlib import Path
from invoke.exceptions import Exit

testy_config = ".testy"


# ---------------------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------------------

# Install the testy framework.
@task
def install(c, branch="develop"):

    # Create application user.
    user = get_value("application", "user")
    create_user(c, user)

    # Create framework directories.
    testy_dir = get_value("application", "testy_dir")
    backup_dir = get_value("application", "backup_dir")
    database_dir = get_value("application", "database_dir")

    for dir in [testy_dir, backup_dir, database_dir]:
        create_directory(c, dir)
    c.sudo(f"chown -R $(whoami):$(whoami) {testy_dir}")

    # Install prerequisite software.
    install_packages(c)

    # Clone repositories.
    for repo in ["testy", "wiredtiger"]:
       git_clone(c, get_value(repo, "git_url"), get_value(repo, "home_dir"))

    # Create symbolic links.
    create_symlinks(c)

    # Build WiredTiger.
    build_wiredtiger(c, branch)

    # Install services.
    # TODO: Update this part of the installation when the service implementation
    #       is complete, and add properties in .testy for the service filenames.
    install_service(c, "backup")
    install_service(c, "crash_test")

    # Print installation summary on success.
    print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print("The testy installation is complete!")
    print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print(f"The testy framework user is '{user}'")
    print(f"The testy framework directory is '{testy_dir}'")
    print(f"The testy workloads are found in '" +
          get_value("application", "workload_dir") + "'")
    print(f"The database directory is '{database_dir}'")
    print(f"The database backup directory is '{backup_dir}'")
    print(f"The WiredTiger home directory is '" +
          get_value("wiredtiger", "home_dir") + "'")
    print(f"The WiredTiger build directory is '" +
          get_value("wiredtiger", "build_dir") + "'")

# Run the populate function as defined in the workload interface file.
@task
def populate(c, workload):

    wif = get_value("application", "workload_dir") + "/" + workload + ".sh"
    command = get_env("environment") + " bash " + wif + " populate"

    if c.sudo(command, user=get_value("application", "user"), warn=True):
        print(f"populate succeeded for workload '{workload}'")
    else:
        print(f"populate failed for workload '{workload}'")

# The workload function takes 3 optional arguments upload, list, describe. If no arguments are 
# provided, the current workload is returned.
@task
def workload(c, upload=None, list=False, describe=None):
    """ Upload, list, and describe workloads. 
    Up three optional arguments can be taken at a time. If more than one option is specified at
    once, they will be executed in the following order (regardless of order they are called): - 
       1. upload
       2. list
       3. describe
    If an option fails at any point, it will print an error message, exit the current option and 
    continue running the following options.  
    A workload must be specified for the describe and upload options.  
    """
    
    cur_workload = get_value("testy", "cur_workload")

    # TODO: Implement list and upload functionality.
    if upload:
        print("Upload to be implemented") 
    if list:
        print("Listing to be implemented")

    # Describes the specified workload by running the describe function as defined in the workload
    # interface file.
    if describe:
        wif = get_value("testy", "workload_dir") + "/" + describe + "/" + describe + ".sh"
        command = wif + " describe"
        result = c.sudo(command, user=get_value("application", "user"), warn=True)
        if not result: 
            print(f"Unable to describe '{describe}' workload")
        elif result.stdout == "":
            print(f"No description provided for workload '{describe}'.")
    
    # If no option has been specified, print the current workload and return as usual.  
    if not describe and not upload and not list:
        if cur_workload:
            print(f"Current workload:\033[1m {cur_workload}\033[0m ")
        else: 
            print("The current workload is unspecified")
    return 

# ---------------------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------------------

# Return the value corresponding to the specified key from the specified section
# of the testy configuration file.
def get_value(section, key):

    parser = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    parser.read(testy_config)

    if section not in parser.sections():
        raise Exit(f"No '{section}' section in file '{testy_config}'.")
    if not parser.has_option(section, key):
        raise Exit(f"No '{key}' option in section '{section}'.")

    return parser.get(section, key)

# Return the key/value pairs in the application section of the testy configuration file
# as a single string of shell environment values.
def get_env(section):

    parser = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    parser.read(testy_config)

    if section not in parser.sections():
        raise Exit(f"No '{section}' section in file '{testy_config}'.")

    env = ""
    for k, v in parser.items(section):
        env += k + "=" + v + " "
    return env

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
def git_clone(c, git_url, local_dir):

    repo = Path(git_url).stem
    if c.run(f"test -d {local_dir}", warn=True):
        print(f"Directory '{local_dir}' exists. " \
              f"Repository '{repo}' will not be cloned.")
    else:
        print(f"Cloning '{repo}' repository ... ", end='', flush=True)
        c.run(f"git clone {git_url} {local_dir}", hide=True)
        print("done!")

# Create framework symlinks.
def create_symlinks(c):

    if not c.run("test -h " + get_value("application", "workload_dir"), warn=True):
        with c.cd(get_value("application", "testy_dir")):
            c.run("ln -s " + get_value("testy", "workload_dir"))

# Build WiredTiger for the specified branch.
def build_wiredtiger(c, branch):

    wt_home_dir = get_value("wiredtiger", "home_dir")
    wt_build_dir = get_value("wiredtiger", "build_dir")

    with c.cd(wt_home_dir):
        print(f"Checking out git branch '{branch}' ... ", end='', flush=True)
        c.run(f"git checkout {branch}")
        c.run("git pull", hide=True)
        c.run("rm -rf build && mkdir build")

    with c.cd(wt_build_dir):
        ninja_build = c.run("which ninja", warn=True, hide=True)

        print("Configuring WiredTiger")
        c.run("cmake ../. -G Ninja") if ninja_build else c.run("cmake ../.")
        print("-- Configuration complete!")

        print("Building WiredTiger")
        if ninja_build:
            c.run("ninja -j $(grep -c ^processor /proc/cpuinfo)")
        else:
             c.run("make -j $(grep -c ^processor /proc/cpuinfo)")
        print("-- Build complete!")

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

# Install services.
def install_service(c, service):

    print(f"Installing service '{service}' ... ", end='', flush=True)
    file = get_value("testy", "service_dir")
    if not c.run(f"test -f {file}", warn=True):
        print("failed")
        print(f"-- Unable to install service: File not found.")
    else:
        c.sudo(f"cp {file} /etc/systemd/system && systemctl daemon-reload")
        print("done!")
