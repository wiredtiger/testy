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

import random
from helper_testy import *

# Setup
connection_config = 'create'
context, connection = setup(connection_config)

# Populate: Create tables.
num_tables = 1000
tables = []
table_config = 'key_format=S,value_format=S'
session = create_session(connection, '')

for i in range(num_tables):
    table_name = "table:test" + str(i)
    table = create_table(session, table_name, table_config)
    tables.append(table)

print("Tables created:", num_tables)

# Populate: Insert random key/value pairs in all tables until reaching a size limit.
kb = 1024
mb = 1024 * kb
gb = 1024 * mb
target_size = 100 * gb
print('Populating the database...', end='')
while True:

    # Select a random table.
    table_idx = random.randint(0, num_tables - 1)

    # Create the insert operation.
    insert_op = Operation(Operation.OP_INSERT, tables[table_idx], Key(Key.KEYGEN_AUTO,
        random.randint(20, 100)), Value(random.randint(20, 100)))

    # Allocate a thread.
    thread = Thread(insert_op)

    # Generate and start the workload.
    pop_workload = Workload(context, thread)
    pop_workload.run(connection)

    # Check the current size of the database ignoring the report file.
    report_file = pop_workload.options.report_file
    if get_dir_size("WT_TEST", pop_workload.options.report_file) > target_size:
        break

print(' DONE')
