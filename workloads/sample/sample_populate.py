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
import signal
import threading as pythread
from workgen import *
from sample_common import *


def signal_handler(signum, frame):
    signame = signal.Signals(signum).name
    print(f"{os.path.basename(__file__)} received signal {signame}.")
    assert signal.Signals(signum) == signal.SIGTERM
    global thread_exit
    thread_exit.set()


def create_tables(connection, num_tables, name_length, table_config):
    assert name_length > 0

    global tables
    session = connection.open_session()
    i = 0

    while i < num_tables and not thread_exit.is_set():
        table_name = "table:" + generate_random_string(name_length)
        # It is possible to have a collision if the table has already been created, simply retry.
        try:
            session.create(table_name, table_config)
            # The GIL guarantees the following to be thread safe.
            tables.append(Table(table_name))
            i += 1
        except wiredtiger.WiredTigerError as e:
            assert "file exists" in str(e).lower()


thread_exit = pythread.Event()
signal.signal(signal.SIGTERM, signal_handler)

# Setup the WiredTiger connection.
context = Context()
connection_config = "create"
connection = open_connection(context, connection_config)

# Create tables.
num_threads = 10
tables_per_thread = 100
num_tables = num_threads * tables_per_thread
tables = []
# This allows enough combinations.
table_name_length = 4
table_config = "key_format=S,value_format=S,exclusive"

threads = []
print(f"Creating {num_tables} tables ...", end='', flush=True)
i = 0
while i < num_threads and not thread_exit.is_set():
    thread = pythread.Thread(target=create_tables, args=(connection, tables_per_thread,
        table_name_length, table_config))
    threads.append(thread)
    thread.start()
    i += 1

for x in threads:
    x.join()
threads = []

print(f" {i} tables created.", flush=True)
if not thread_exit.is_set():
    assert len(tables) == num_tables
 
# Insert random key/value pairs in all tables until it reaches the size limit.
kb = 1024
mb = 1024 * kb
gb = 1024 * mb

min_record_size = 1
max_record_size = 100 * kb

current_db_size = 0
target_db_size = 100 * gb
progress_pct = 0

if not thread_exit.is_set():
    print("", end=f"\rPopulating the database ... {progress_pct}%", flush=True)

while current_db_size < target_db_size and not thread_exit.is_set():

    # Select a random table.
    table_idx = random.randint(0, num_tables - 1)

    # Create the insert operation.
    key_size = random.randint(min_record_size + 1, max_record_size)
    value_size = random.randint(min_record_size, max_record_size)
    key = Key(Key.KEYGEN_AUTO, key_size)
    value = Value(value_size)
    insert_op = Operation(Operation.OP_INSERT, tables[table_idx], key, value)

    # Allocate a thread.
    thread = Thread(insert_op)

    # Start the workload.
    # The next generated key/value pair may not fit in the randomly generated size, simply retry if
    # this is the case.
    pop_workload = Workload(context, thread)
    try:
        pop_workload.run(connection)
        current_db_size += (key_size + value_size)
    except Exception as e:
        assert "too large for" in str(e).lower()

    if ((current_db_size * 100) // target_db_size) > progress_pct:
        checkpoint(context, connection)
        print("", end=f"\rPopulating the database ... {progress_pct}%", flush=True)
        progress_pct += 1

if not thread_exit.is_set():
    print("", end="\rPopulating the database ... Done.")

# Finish with a checkpoint to make all data durable.
checkpoint(context, connection)
connection.close()
print(f"\nDatabase populated with {current_db_size / 1e9} GB of data.")
