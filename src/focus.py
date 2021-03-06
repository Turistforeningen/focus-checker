import multiprocessing
import os
import pylibmc
import pyodbc
from raven import Client
import signal
import time

from logger import logger
from secrets import secrets

if 'DEVELOPMENT' in os.environ:
    raven = Client()
else:
    raven = Client(secrets['SENTRY_DSN'])


def main():
    # How frequent to attempt connection in seconds. Should be low enough to
    # discover a non-working connection as soon as possible, but high enough not
    # to cause significant load on the database.
    check_interval = 1

    # How long to wait for connection before timing out. Applies both to
    # pyodbc's internal timeout mechanism and our own hard process cutoff
    # timeout. In seconds.
    timeout = 5

    # How long the stored value should be valid. Should never be shorter than
    # the value of `check_interval` or `timeout`. In seconds.
    cache_time = 10

    logger.info(
        "initializing with check_interval=%s, timeout=%s, cache_time=%s" % (
            check_interval,
            timeout,
            cache_time,
        )
    )

    host, port = secrets['DATABASES_FOCUS_HOST_PROD'].split(',')
    connection_string = ';'.join([
        'DRIVER={FreeTDS}',
        'SERVER=%s' % host,
        'PORT=%s' % port,
        'DATABASE=%s' % secrets['DATABASES_FOCUS_NAME_PROD'],
        'UID=%s' % secrets['DATABASES_FOCUS_USER_PROD'],
        'PWD=%s' % secrets['DATABASES_FOCUS_PASSWORD_PROD'],
    ])

    mc = pylibmc.Client(
        ["memcached"],
        binary=True,
        behaviors={"tcp_nodelay": True, "ketama": True},
    )

    logger.debug("memcached connection established")

    def attempt_connection():
        connection = pyodbc.connect(connection_string, timeout=timeout)
        cursor = connection.cursor()
        cursor.execute('select @@version').fetchall()
        cursor.close()
        connection.close()

    previous_availability = None
    while True:
        # Note that `timeout` argument will *not* ensure consistent timeouts for
        # any connection problem. It sets the ODBC API connection attribute
        # SQL_ATTR_LOGIN_TIMEOUT, but not SQL_ATTR_CONNECTION_TIMEOUT.
        # See https://github.com/mkleehammer/pyodbc/issues/106
        # Therefore, perform the connection in a separate process. pyodbc
        # acquires the GIL lock during connection, so signalling or threading
        # wouldn't work here.
        connection_process = multiprocessing.Process(target=attempt_connection)
        connection_process.start()
        connection_process.join(timeout)

        # If the connection attempt didn't finish, terminate it; it will get a
        # non-zero exit code
        if connection_process.is_alive():
            # connection_process.terminate() sends SIGINT and pyodbc doesn't
            # seem to respond to that while blocking. It does respond to SIGHUP,
            # so send that.
            os.kill(connection_process.pid, signal.SIGHUP)
            connection_process.join()

        focus_available = connection_process.exitcode == 0
        mc.set("focus.connection", focus_available, time=cache_time)

        if previous_availability != focus_available:
            logger.info("Focus availability changed to %s" % focus_available)
            previous_availability = focus_available

        time.sleep(check_interval)

if __name__ == '__main__':
    try:
        main()
        raise Exception("Main loop finished unexpectedly")
    except Exception:
        raven.captureException()
        raise
