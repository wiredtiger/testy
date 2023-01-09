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

from sample_common import *

# Set up the WiredTiger connection.
context = Context()
connection = open_connection(context)

# Define the workload.
workload = Workload(context)

# Add a prefix to the created table names.
workload.options.create_prefix = "table_"

# Create one table every 30 seconds when the database size is less than 120 GB.
workload.options.create_interval = 30
workload.options.create_count = 1
workload.options.create_trigger = 120 * 1024
workload.options.create_target = 120 * 1024

# Drop five tables every 90 seconds when the database size exceeds 120 GB. Stop
# dropping tables when the database size goes below 80 GB.
workload.options.drop_interval = 90
workload.options.drop_count = 5
workload.options.drop_trigger = 120 * 1024
workload.options.drop_target = 80 * 1024

# Set the workload runtime to maximum value (~68 years).
workload.options.run_time = 2147483647

# Run the workload.
ret = workload.run(connection)
assert ret == 0, ret

# Close the connection.
connection.close()

print(f"{__file__} exited.")
