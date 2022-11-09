# fabfile.py
# Remote management commands for testy: A WiredTiger 24/7 workload testing framework.

import configparser
from fabric import task
from invoke.exceptions import Exit

testy_config = ".testy"


# ---------------------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------------------

# Run the populate function as defined in the workload interface file "workload.sh".
@task
def populate(c, workload=None):

    if not workload:
        raise Exit("Please specify a workload argument.")

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

    config = configparser.ConfigParser()
    config.read(testy_config)

    if section not in config.sections():
        raise Exit(f"No '{section}' section in file '{testy_config}'.")
    if not config.has_option(section, key):
        raise Exit(f"No '{key}' option in section '{section}'.")

    return config.get(section, key)

# Return the key/value pairs in the environment section of the testy configuration file
# as a single string of shell environment values.    
def get_config_env(section):

    config = configparser.ConfigParser()
    config.read(testy_config)

    if section not in config.sections():
        raise Exit(f"No '{section}' section in file '{testy_config}'.")

    env = ""
    for k, v in config.items(section):
        env += k + "=" + v + " "
    return env
