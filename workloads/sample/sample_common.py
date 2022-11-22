#!/usr/bin/env python
#
# Public Domain 2014-present MongoDB, Inc.
# Public Domain 2008-2014 WiredTiger, Inc.
#
# This is free and unencumbered software released into the public domain.
#
# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.
#
# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#

import os, random, string
from workgen import *


def checkpoint(context, connection):
    checkpoint_op = Operation(Operation.OP_CHECKPOINT, "")
    thread = Thread(checkpoint_op)
    checkpoint_workload = Workload(context, thread)
    checkpoint_workload.run(connection)


def generate_random_string(length):
    assert length > 0
    characters = string.ascii_letters + string.digits
    str = ''.join(random.choice(characters) for _ in range(length))
    return str


# Get the directory size in bytes excluding Workgen files.
def get_dir_size(dir):

    with os.scandir(dir) as entries:
        total_size = 0
        for entry in entries:
            # Workgen generates a statistics file called "workload.stat" that needs to be ignored.
            if entry.is_file() and entry.name not in "workload.stat":
                total_size += entry.stat().st_size
        return total_size


# Return the total RAM in bytes.
def get_total_os_memory():
    return int(os.popen("free -t -b").readlines()[-1].split()[1:][0])


# Open a WiredTiger connection allocating a specific cache size.
# The allocated cache size follows what MongoDB does: (total memory available - 1GB) / 2.
def open_connection(context, config = ''):
    total_memory = get_total_os_memory()
    cache_size_gb = int(((total_memory - 1e9) / 2) / 1e9)

    connection_config = f"{config},cache_size={cache_size_gb}GB"
    connection = context.wiredtiger_open(connection_config)
    return connection
