import sys
import configparser as cp

# Return the value corresponding to the specified key from the specified section
# of the testy configuration file.
def get_value(config, section, key):

    parser = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    parser.read(config)

    if section not in parser.sections():
        raise ValueError(f"No '{section}' section in file '{config}'.")
    if not parser.has_option(section, key):
        raise ValueError(f"No '{key}' option in section '{section}'.")

    print(parser.get(section, key), end='', flush=True)

# Return the key/value pairs in the specified section of the testy configuration file
# as a single string of shell environment values.
def get_env(config, section):

    parser = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    parser.read(config)

    if section not in parser.sections():
        raise ValueError(f"No '{section}' section in file '{config}'.")

    env = ""
    for k, v in parser.items(section):
        env += k + "=" + v + " "
    print(env, end='', flush=True)

# Return a string suitable for generating a drop-in .conf file of environment
# values for the testy systemd services.
def get_systemd_service_conf(config, section):

    parser = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    parser.read(config)

    if section not in parser.sections():
        raise ValueError(f"No '{section}' section in file '{config}'.")

    env = "[Service]"
    for k, v in parser.items(section):
        env += "\nEnvironment=\"" + k + "=" + v + "\""
    print(env, end='', flush=True)

# Set the value corresponding to the specified key from the specified section
# of the testy configuration file.
def set_value(config, section, key, value):

    parser = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    parser.read(config)

    if section not in parser.sections():
        parser.add_section(section)
        print(f"Creating '{section}' section in '{config}'.")
    parser.set(section, key, value)
    print(f"Setting '{key}' to '{value}'.", end='', flush=True)

    with open(config, 'w') as configfile:
        parser.write(configfile)

# This allows us to call script functions by name from the command line with an
# arbitrary number of parameters. Example usage is:
# 
#   $ python3 testy_parse.py get_env '/srv/testy/.testy' 'environment'
#   $ python3 testy_parse.py get_value '/srv/testy/.testy' 'application' 'user'
#
if __name__ == "__main__":

    globals()[sys.argv[1]](*sys.argv[2:])
