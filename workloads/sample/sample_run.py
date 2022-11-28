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
import threading as pythread
import signal
from time import sleep
from sample_common import *


def signal_handler(signum, frame):
    signame = signal.Signals(signum).name
    print(f"{__file__} received signal {signame}.")
    assert signal.Signals(signum) == signal.SIGTERM
    global thread_exit
    thread_exit.set()


# Create a table periodically.
def create(connection, interval_sec, name_length, table_config):
    assert name_length > 0

    global tables
    session = connection.open_session()

    while not thread_exit.is_set():
        # It is possible to have a collision if the table has already been created but it should be
        # rare.
        table_name = "table:" + generate_random_string(name_length)
        try:
            session.create(table_name, table_config)
            tables.append(Table(table_name))
        except wiredtiger.WiredTigerError as e:
            assert "file exists" in str(e).lower()
        thread_exit.wait(interval_sec)


thread_exit = pythread.Event()
signal.signal(signal.SIGTERM, signal_handler)

# Delete random tables when the database size is not within range until the target is reached. The
# threshold and the target are in bytes.
def delete_table(connection, db_dir, threshold, target):
    assert target <= threshold

    global tables
    session = connection.open_session()

    while is_running:
        sleep(1)

        num_tables = len(tables)
        while is_running and num_tables > 0 and get_db_size(db_dir) >= target:

            # Select a random table to delete.
            table_idx = random.randint(0, num_tables - 1)
            table_name = "table:" + tables[table_idx]._uri

            # It is possible that the selected table cannot be dropped if it is being used, simply
            # retry.
            try:
                session.drop(table_name)
                del tables[table_idx]
            except Exception as e:
                assert "resource busy" in str(e).lower()


# Setup the WiredTiger connection.
context = Context()
connection = open_connection(context)
is_running = True

# Retrieve existing tables in the database directory.
tables = get_tables(context.args.home)
threads = []

# Create tables periodically.
table_name_length = 4
table_config = "key_format=S,value_format=S,exclusive"
create_interval_sec = 60

create_thread = pythread.Thread(target=create, args=(connection, create_interval_sec,
    table_name_length, table_config))
threads.append(create_thread)
create_thread.start()

# Delete tables when the database size is too big.
kb = 1024
mb = 1024 * kb
gb = 1024 * mb

drop_threshold = 120 * gb
drop_target = 100 * gb
drop_thread = pythread.Thread(target=delete_table, args=(connection, context.args.home,
    drop_threshold, drop_target))
threads.append(drop_thread)
drop_thread.start()

for thread in threads:
    thread.join()
threads = []

# Finish with a checkpoint to make all data durable.
checkpoint(context, connection)
connection.close()

print(f"{__file__} exited.")
