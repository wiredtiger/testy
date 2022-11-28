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

import threading as pythread
import signal
from time import sleep
from sample_common import *

signal_exit = False

def signal_handler(signum, frame):
    assert signal.Signals(signum) == signal.SIGTERM
    global signal_exit 
    signal_exit= True


# Create a table periodically.
def create_table(connection, interval_sec, name_length, table_config):
    assert name_length > 0

    session = connection.open_session()

    while create_tables and not signal_exit:
        success = False
        sleep(interval_sec)

        # It is possible to have a collision if the table has already been created, keep trying.
        while create_tables and not signal_exit and not success:
            table_name = "table:" + generate_random_string(name_length)
            try:
                session.create(table_name, table_config)
                success = True
            except wiredtiger.WiredTigerError as e:
                assert "file exists" in str(e).lower()


signal.signal(signal.SIGTERM, signal_handler)

# Setup the WiredTiger connection.
context = Context()
connection = open_connection(context)

threads = list()

# Create tables periodically.
table_name_length = 4
table_config = "key_format=S,value_format=S,exclusive"
interval_sec = 60
create_tables = True

thread = pythread.Thread(target=create_table, args=(connection, interval_sec, table_name_length,
    table_config))
threads.append(thread)
thread.start()

# TODO: Make sure to stop all threads when the workload stops. For now, sleep for some time.
workload_duration = 300
print(f"Running for {workload_duration} seconds.")
sleep(workload_duration)

create_tables = False
for x in threads:
    x.join()
threads = []

# Finish with a checkpoint to make all data durable.
checkpoint(context, connection)
connection.close()

if signal_exit:
    print("Run stopped.")
else:
    print("Run has complete.")

