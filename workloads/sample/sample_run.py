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

    session = connection.open_session()

    while not thread_exit.is_set():
        # It is possible to have a collision if the table has already been created but it should be
        # rare.
        table_name = "table:" + generate_random_string(name_length)
        try:
            session.create(table_name, table_config)
        except wiredtiger.WiredTigerError as e:
            assert "file exists" in str(e).lower()
        thread_exit.wait(interval_sec)


thread_exit = pythread.Event()
signal.signal(signal.SIGTERM, signal_handler)

# Setup the WiredTiger connection.
context = Context()
connection = open_connection(context)

threads = list()

# Create tables periodically.
table_name_length = 4
table_config = "key_format=u,value_format=u,exclusive"
create_interval_sec = 60

create_thread = pythread.Thread(target=create, args=(connection, create_interval_sec,
    table_name_length, table_config))
threads.append(create_thread)
create_thread.start()

for thread in threads:
    thread.join()
threads = []

# Finish with a checkpoint to make all data durable.
checkpoint(context, connection)
connection.close()

print(f"{__file__} exited.")
