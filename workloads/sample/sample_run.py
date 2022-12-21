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

import threading as pythread
import re, signal
from sample_common import *
from pathlib import Path

def signal_handler(signum, frame):
    signame = signal.Signals(signum).name
    print(f"{__file__} received signal {signame}.")
    assert signal.Signals(signum) == signal.SIGTERM
    global thread_exit
    thread_exit.set()

# Get a list of all WiredTiger tables in the database directory.
def get_tables(path):
    return [Table(f"table:{f.stem}") for f in path.glob("*.wt") if not f.name.startswith("WiredTiger")]

# Get the database size in bytes.
def get_db_size():
    return sum(os.path.getsize(f) for f in os.listdir() if re.match(r"(.*.wt$|^WiredTiger.*)", f))

# Create a table periodically.
def create(connection, interval_sec, name_length, table_config):
    assert name_length > 0

    global tables
    session = connection.open_session()

    while not thread_exit.is_set():
        table_name = "table:" + generate_random_string(name_length)
        # It is possible to have a collision if we randomly generate a table name that matches
        # the name of an existing table.
        try:
            session.create(table_name, table_config)
            tables.append(Table(table_name))
        except wiredtiger.WiredTigerError as e:
            assert "file exists" in str(e).lower()

        thread_exit.wait(interval_sec)

# Check if the database size exceeds a maximum threshold at regular intervals. If so,
# randomly select tables to drop until a target size is reached.
def drop(connection, drop_interval_sec, db_size_max, db_size_target):

    global tables
    session = connection.open_session()

    while not thread_exit.is_set():

        db_size = get_db_size()
        if db_size > db_size_max:

            num_tables = len(tables)
            while num_tables > 0 and db_size >= db_size_target:

                # Select a random table to delete.
                table_idx = random.randint(0, num_tables - 1)
                table_name = tables[table_idx]._uri

                # If a table is in use it cannot be dropped. Simply select a different one.
                try:
                    session.drop(table_name)
                    del tables[table_idx]
                except Exception as e:
                    assert "resource busy" in str(e).lower()

                num_tables = len(tables)
                db_size = get_db_size()

        thread_exit.wait(drop_interval_sec)


thread_exit = pythread.Event()
signal.signal(signal.SIGTERM, signal_handler)

# Set up the WiredTiger connection.
context = Context()
connection = open_connection(context)

# Change to database directory.
path = Path(context.args.home)
os.chdir(path)

tables = get_tables(path)
threads = []

# Create tables periodically.
table_name_length = 4
table_config = "key_format=u,value_format=u,exclusive"
create_interval_sec = 60

create_thread = pythread.Thread(target=create,
    args=(connection, create_interval_sec, table_name_length, table_config))
threads.append(create_thread)
create_thread.start()

# Drop randomly selected tables when the database gets too large.
gb = 1024 * 1024 * 1024
db_size_max = 120 * gb
db_size_target = 100 * gb
drop_interval_sec = 90

drop_thread = pythread.Thread(target=drop,
    args=(connection, drop_interval_sec, db_size_max, db_size_target))
threads.append(drop_thread)
drop_thread.start()

for thread in threads:
    thread.join()
threads = []

# Finish with a checkpoint to make all data durable.
checkpoint(context, connection)
connection.close()

print(f"{__file__} exited.")
