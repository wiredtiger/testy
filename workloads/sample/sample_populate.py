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

import os
import random
import threading as pythread
from workgen import *


def create_table(connection, start, end, table_config):
    """Creates a table"""
    global tables
    tmp_tables = []

    session = connection.open_session()
    for i in range(start, end):
        table_name = "table:test" + str(i)
        session.create(table_name, table_config)
        tmp_tables.append(Table(table_name))

    lock = pythread.Lock()
    with lock:
        tables = tables + tmp_tables


def get_dir_size(dir, ignored_files = []):
    """Gets the size in bytes of a directory"""
    with os.scandir(dir) as entries:
        total_size = 0
        for entry in entries:
            if entry.is_file() and entry.name not in ignored_files:
                total_size += entry.stat().st_size
        return total_size


# Setup
connection_config = 'create'
context = Context()
connection = context.wiredtiger_open(connection_config)

# Create tables.
num_tables = 1000
tables = []
table_config = 'key_format=S,value_format=S'

num_threads = 10
threads = list()
if num_threads > num_tables:
    num_threads = num_tables
table_per_thread = num_tables // num_threads
remainder = num_tables % num_threads

# Split the work among the threads.
for i in range(0, table_per_thread * num_threads, table_per_thread):
    start = i
    end = i + table_per_thread
    x = pythread.Thread(target=create_table, args=(connection, start, end, table_config))
    threads.append(x)
    x.start()

# Use an extra thread to do the remaining work.
if remainder > 0:
    start = table_per_thread * num_threads
    end = num_tables
    x = pythread.Thread(target=create_table, args=(connection, start, end, table_config))
    threads.append(x)
    x.start()

for x in threads:
    x.join()

print("Tables created:", num_tables)
assert len(tables) == num_tables

# Insert random key/value pairs in all tables until reaching a size limit.
kb = 1024
mb = 1024 * kb
gb = 1024 * mb

min_record_size = 1
max_record_size = 100 * kb

current_dir_size = 0
target_size = 100 * gb

print('Populating the database...', end='')
while current_dir_size < target_size:

    # Select a random table.
    table_idx = random.randint(0, num_tables - 1)

    # Create the insert operation.
    insert_op = Operation(Operation.OP_INSERT, tables[table_idx], Key(Key.KEYGEN_AUTO,
        random.randint(min_record_size, max_record_size)), Value(random.randint(min_record_size + 1, max_record_size)))

    # Allocate a thread.
    thread = Thread(insert_op)

    # Generate and start the workload.
    pop_workload = Workload(context, thread)
    pop_workload.run(connection)

    # Check the current size of the database ignoring the report file.
    current_dir_size = get_dir_size(context.args.home, pop_workload.options.report_file)

# Finish with a checkpoint to make all data durable.
checkpoint_op = Operation(Operation.OP_CHECKPOINT, "")
thread = Thread(checkpoint_op)
checkpoint_workload = Workload(context, thread)
checkpoint_workload.run(connection)

print(' DONE')
