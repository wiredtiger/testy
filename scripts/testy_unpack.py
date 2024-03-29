import shutil
import sys

# Unpacks an archive to a given destination. The shutil library handles the archive format.
def unpack_archive(src, dest):
    shutil.unpack_archive(src, dest)

# This allows us to call script functions by name from the command line with an
# arbitrary number of parameters. Example usage is:
# 
#   $ python3 testy_unpack.py unpack_archive 'src_path' 'dest_path'
#
if __name__ == "__main__":

    globals()[sys.argv[1]](*sys.argv[2:])
