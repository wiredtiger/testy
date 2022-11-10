# fabfile.py
# Remote management commands for testy: A WiredTiger 24/7 workload testing framework.

import configparser
from fabric import task
from invoke.exceptions import Exit

testy_config = ".testy"


# ---------------------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------------------

# Install the testy framework.
@task
def install(c, branch="develop"):

    # Create testy user.
    user = get_config_value("testy", "user")
    create_user(c, user)

    # Create framework directories.
    testy_dir = get_config_value("environment", "testy_dir")
    backup_dir = get_config_value("environment", "backup_dir")
    database_dir = get_config_value("environment", "database_dir")
    create_directory(c, testy_dir)
    create_directory(c, backup_dir)
    create_directory(c, database_dir)
    c.sudo(f"chown -R $(whoami):$(whoami) {testy_dir}")

    # Install prerequisite software.
    install_packages(c)

    # Clone repositories.
    git_clone(c, get_config_value("testy", "git_remote_url"),
              get_config_value("testy", "git_checkout_dir"))

    git_clone(c, get_config_value("wiredtiger", "git_remote_url"),
              get_config_value("wiredtiger", "git_checkout_dir"))

    # Build WiredTiger.
    build_wiredtiger(c, branch)

    # Install services.
    install_service(c, "backup")

    # Print installation summary on success.
    wt_home_dir = get_config_value("environment", "wt_home_dir")
    wt_build_dir = get_config_value("environment", "wt_build_dir")
    workload_dir = get_config_value("environment", "workload_dir")

    print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print("The testy installation is complete!")
    print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print(f"The testy framework user is '{user}'")
    print(f"The testy framework directory is '{testy_dir}'")
    print(f"The testy workloads are found in '{workload_dir}'")
    print(f"The database directory is '{database_dir}'")
    print(f"The database backup directory is '{backup_dir}'")
    print(f"The WiredTiger home directory is '{wt_home_dir}'")
    print(f"The WiredTiger build directory is '{wt_build_dir}'")

# Run the populate function as defined in the workload interface file "workload.sh".
@task
def populate(c, workload):

    wif = get_config_value("environment", "workload_dir") + "/" + workload + ".sh"
    command = get_config_env("environment") + " bash " + wif + " populate"
    status = c.sudo(command,  user="testy", warn=True)

    if status.return_code == 0:
        print(f"populate succeeded for workload '{workload}'")
    else:
        print(f"populate failed for workload '{workload}'")


# ---------------------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------------------

# Return the value corresponding to the specified key from the specified section
# of the testy configuration file.
def get_config_value(section, key):

    parser = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    parser.read(testy_config)

    if section not in parser.sections():
        raise Exit(f"No '{section}' section in file '{testy_config}'.")
    if not parser.has_option(section, key):
        raise Exit(f"No '{key}' option in section '{section}'.")

    return parser.get(section, key)

# Return the key/value pairs in the environment section of the testy configuration file
# as a single string of shell environment values.    
def get_config_env(section):

    parser = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
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
        c.sudo(f"usermod -aG sudo {username}", warn=True)
    elif c.run("getent group wheel", warn=True, hide=True):
        c.sudo(f"usermod -aG wheel {username}", warn=True)
    c.sudo(f"echo '{username} ALL=(ALL:ALL) NOPASSWD:ALL' | " \
           f"sudo tee /etc/sudoers.d/{username}-user >/dev/null", user="root")

    result = c.sudo("groups", user=username, hide=True)
    print(f"Groups for user '{username}' are (" + result.stdout.strip() + ")")

# Create framework directories.
def create_directory(c, dir):

    if c.sudo(f"test -d {dir}", warn=True):
        print(f"Directory '{dir}' exists.")
    else:
        print(f"Creating directory '{dir}' ...")
        if c.sudo(f"mkdir -p {dir}", warn=True).failed:
            raise Exit(f"Error: Unable to create directory '{dir}'")

# Clone git repository.
def git_clone(c, git_url, local_dir):

    if c.run(f"test -d {local_dir}", warn=True):
        print(f"Directory '{local_dir}' exists. " \
              f"Repository '{git_url}' will not be cloned.")
    else:
        print("Cloning repository ...")
        c.run(f"git clone {git_url} {local_dir}", hide=True)

# Build WiredTiger for the specified branch.
def build_wiredtiger(c, branch):

    wt_home_dir = get_config_value("environment", "wt_home_dir")
    wt_build_dir = get_config_value("environment", "wt_build_dir")

    with c.cd(wt_home_dir):
        print(f"Checking out git branch '{branch}' ...")
        c.run(f"git pull && git checkout {branch}")
        c.run("rm -rf build && mkdir build")

    with c.cd(wt_build_dir):
        #ninja_build = c.run("which ninja", warn=True, hide=True)
        print("Configuring WiredTiger ...")
        c.run("cmake ../.")
        print("Building WiredTiger ...")
        c.run("make")
        
    print("... done!")

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
    packages = ["cmake", "cmake-curses-gui", "ccache", "ninja-build",
                "python3-dev", "swig", "libarchive"]
    print("Installing required software packages ...")

    if is_rpm:
        for package in packages:
            if c.run(f"rpm -qa | grep {package}", warn=True, hide=True):
                if c.run(f"{installer} list installed {package}", warn=True, hide=True):
                    print(f" . Package '{package}' is already installed.")
                else:
                    c.sudo(f"{installer} -y install {package}", hide=True)
                    print(f" . Installed package '{package}'.")
    else:
        for package in packages:
            if c.run(f"dpkg-query -l | grep {package}", warn=True, hide=True):
                if c.run(f"dpkg -s {package}", warn=True, hide=True):
                    print(f" . Package '{package}' is already installed.")
                else:
                    c.sudo(f"{installer} -y install {package}", hide=True)
                    print(f" . Installed package '{package}'.")

    # Attempt to pip install ninja if it was not available through the package manager.
    if not c.run("which ninja", warn=True, hide=True):
        if c.sudo(f"python3 -m pip install ninja", warn=True, hide=True):
            print(f" . Installed package 'ninja'.")

# Install services.
def install_service(c, service):

    print(f"Installing service '{service}' ...")
