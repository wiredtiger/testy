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

from runner import *
from workgen import *


def create_session(connection, session_config = ''):
    """Creates a session

    Args:
        connection (Connection): WiredTiger connection
        session_config (str, optional): Session configuration

    Returns:
        Session: WiredTiger session
    """
    session = connection.open_session(session_config)
    return session


def create_table(session, table_name, table_config = ''):
    """Creates a table

    Args:
        session (Session): WiredTiger session
        table_name (str): Table name
        table_config (str, optional): Table configuration

    Returns:
        Table: Workgen Table
    """
    session.create(table_name, table_config)
    return Table(table_name)


def get_dir_size(dir, ignored_files = []):
    """Returns the top-level directory size

    Args:
        dir (str): The directory location
        filters (str[], optional): Ignored files

    Returns:
        int: The size of the top-level directory
    """
    with os.scandir(dir) as entries:
        total_size = 0
        for entry in entries:
            if entry.is_file() and entry.name not in ignored_files:
                total_size += entry.stat().st_size
        return total_size


def setup(connection_config):
    """Creates a Workgen Context and a WiredTiger connection

    Args:
        connection_config (str): Connection configuration

    Returns:
        Context: Workgen Context
        Connection: WiredTiger connection
    """
    context = Context()
    connection = context.wiredtiger_open(connection_config)
    return context, connection
