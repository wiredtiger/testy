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

import os
from runner import *
from workgen import *

# Return the total RAM in bytes.
def get_total_os_memory():
    return int(os.popen("free -t -b").readlines()[-1].split()[1:][0])

# Set up the WiredTiger connection.
context = Context()
# The allocated cache size follows what MongoDB does: (total memory available - 1GB) / 2.
cache_size_gb = int(((get_total_os_memory() - 1e9) / 2) / 1e9)
connection_config = f"cache_size={cache_size_gb}GB,checkpoint=(wait=60),create=true,log=(enabled=true),statistics=(fast),statistics_log=(wait=60,json)"
connection = context.wiredtiger_open(connection_config)

# Make smaller inserts more frequently and large ones less frequently.
insert_op_1 = 100 * (Operation(Operation.OP_INSERT, Key(Key.KEYGEN_APPEND, 512), Value(1024))) + \
              Operation(Operation.OP_SLEEP, "1")
insert_op_2 = 50 * (Operation(Operation.OP_INSERT, Key(Key.KEYGEN_APPEND, 512), Value(10*1024))) + \
              Operation(Operation.OP_SLEEP, "2")
insert_op_3 = 20 * (Operation(Operation.OP_INSERT, Key(Key.KEYGEN_APPEND, 512), Value(100*1024))) + \
              Operation(Operation.OP_SLEEP, "5")
insert_thread = Thread(10*insert_op_1 + 5*insert_op_2 + insert_op_3)

# Perform updates at random using the pareto distribution. Make smaller updates more frequently
# and large ones less frequently.
update_op_1 = 100 * (Operation(Operation.OP_UPDATE, Key(Key.KEYGEN_PARETO, 512, ParetoOptions(1)),
            Value(1024))) + Operation(Operation.OP_SLEEP, "1")
update_op_2 = 50 * (Operation(Operation.OP_UPDATE, Key(Key.KEYGEN_PARETO, 512, ParetoOptions(1)),
            Value(10*1024))) + Operation(Operation.OP_SLEEP, "2")
update_op_3 = 20 * (Operation(Operation.OP_UPDATE, Key(Key.KEYGEN_PARETO, 512, ParetoOptions(1)),
            Value(100*1024))) + Operation(Operation.OP_SLEEP, "5")
update_thread = Thread(10*update_op_1 + 5*update_op_2 + update_op_3)

# Read operations.
read_op = 20 * (Operation(Operation.OP_SEARCH, Key(Key.KEYGEN_APPEND, 512), Value(1))) * 10 + \
          Operation(Operation.OP_SLEEP, "5")
read_thread = Thread(read_op)

# Delete operations.
delete_op = 20 * (Operation(Operation.OP_REMOVE, Key(Key.KEYGEN_APPEND, 512), Value(1))) + \
            Operation(Operation.OP_SLEEP, "5")
delete_thread = Thread(delete_op)

# Transactions.
txn_op = txn(2*insert_op_1 + 2*update_op_1 + 2*delete_op + 2*read_op)
txn_thread = Thread(txn_op)

# Define the workload using the above operations.
workload = Workload(context, 10*insert_thread + 10*update_thread + 10*read_thread + \
           5*delete_thread + txn_thread)

# Disable generation of stats.
workload.options.report_enabled = False

# Add a prefix to the table names.
workload.options.create_prefix = "table_"

# Target database size in GB.
db_size_target_gb = 40

# Create one table every 30 seconds until we have reached the target database size.
workload.options.create_interval = 30
workload.options.create_count = 1
workload.options.create_trigger = db_size_target_gb * 1024
workload.options.create_target = db_size_target_gb * 1024
workload.options.max_num_files = 1000

# Drop five tables every 90 seconds when the database size exceeds the target database size margin.
# Stop when the database size is below the target size margin.
workload.options.drop_interval = 90
workload.options.drop_count = 5
workload.options.drop_trigger = (db_size_target_gb + 20) * 1024
workload.options.drop_target = (db_size_target_gb - 20) * 1024

# Enable mirror tables and random table values.
workload.options.mirror_tables = True
workload.options.random_table_values = True

# Enable background compaction with a compaction threshold of 100MB.
#workload.options.background_compact = 100

# Set the workload runtime to maximum value (~68 years).
workload.options.run_time = 2147483647

# Run the workload.
ret = workload.run(connection)
assert ret == 0, ret

# Close the connection.
connection.close()

print(f"{__file__} exited.")
