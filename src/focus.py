import multiprocessing
import os
import pylibmc
import pyodbc
from raven import Client
import signal

from secrets import secrets

if 'DEVELOPMENT' in os.environ:
    raven = Client()
else:
    raven = Client(secrets['SENTRY_DSN'])


def main():
    host, port = secrets['DATABASES_FOCUS_HOST_PROD'].split(',')
    connection_string = ';'.join([
        'DRIVER={FreeTDS}',
        'SERVER=%s' % host,
        'PORT=%s' % port,
        'DATABASE=%s' % secrets['DATABASES_FOCUS_NAME_PROD'],
        'UID=%s' % secrets['DATABASES_FOCUS_USER_PROD'],
        'PWD=%s' % secrets['DATABASES_FOCUS_PASSWORD_PROD'],
    ])

    timeout = 5
    cache_time = 10

    def attempt_connection():
        connection = pyodbc.connect(connection_string, timeout=timeout)
        cursor = connection.cursor()
        cursor.execute('select @@version').fetchall()
        cursor.close()
        connection.close()

    # Note that `timeout` argument will *not* ensure consistent timeouts for any
    # connection problem. It sets the ODBC API connection attribute
    # SQL_ATTR_LOGIN_TIMEOUT, but not SQL_ATTR_CONNECTION_TIMEOUT.
    # See https://github.com/mkleehammer/pyodbc/issues/106
    # Therefore, perform the connection in a separate process. pyodbc acquires
    # the GIL lock during connection, so signalling or threading wouldn't work
    # here.
    connection_process = multiprocessing.Process(target=attempt_connection)
    connection_process.start()
    connection_process.join(timeout)

    # If the connection attempt didn't finish, terminate it; it will get a
    # non-zero exit code
    if connection_process.is_alive():
        # connection_process.terminate() sends SIGINT and pyodbc doesn't seem to
        # respond to that while blocking. It
        # does respond to SIGHUP, so send that.
        os.kill(connection_process.pid, signal.SIGHUP)
        connection_process.join()

    focus_available = connection_process.exitcode == 0
    mc = pylibmc.Client(
        ["memcached"],
        binary=True,
        behaviors={"tcp_nodelay": True, "ketama": True},
    )
    mc.set("focus.connection", focus_available, time=cache_time)

if __name__ == '__main__':
    try:
        main()
    except Exception:
        raven.captureException()
        raise
