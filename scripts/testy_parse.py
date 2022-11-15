import sys
import configparser as cp

# Return the value corresponding to the specified key from the specified section
# of the testy configuration file.
def get_value(config, section, key):

    parser = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    parser.read(config)

    if section not in parser.sections():
        raise ValueError(f"No '{section}' section in file '{testy_config}'.")
    if not parser.has_option(section, key):
        raise ValueError(f"No '{key}' option in section '{section}'.")

    print(parser.get(section, key), end='', flush=True)

# Return the key/value pairs in the specified section of the testy configuration file
# as a single string of shell environment values.
def get_env(config, section):

    parser = cp.ConfigParser(interpolation=cp.ExtendedInterpolation())
    parser.read(config)

    if section not in parser.sections():
        raise ValueError(f"No '{section}' section in file '{testy_config}'.")

    env = ""
    for k, v in parser.items(section):
        env += k + "=" + v + " "
    print(env, end='', flush=True)

#
if __name__ == "__main__":

    globals()[sys.argv[1]](*sys.argv[2:])
