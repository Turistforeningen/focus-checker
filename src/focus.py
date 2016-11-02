import multiprocessing
import os
import pylibmc
import pyodbc
import signal

from secrets import secrets

def main():
    host, port = secrets['DATABASES_FOCUS_HOST_TEST'].split(',')
    connection_string = 'DRIVER={Freetds};SERVER=%s;PORT=%s;DATABASE=%s;UID=%s;PWD=%s' % (
        host,
        port,
        secrets['DATABASES_FOCUS_NAME_PROD'],
        secrets['DATABASES_FOCUS_USER_TEST'],
        secrets['DATABASES_FOCUS_PASSWORD_TEST'],
    )

    timeout = 5
    cache_time = 10

    def attempt_connection():
        connection = pyodbc.connect(connection_string, timeout=timeout)
        cursor = connection.cursor()
        cursor.execute('select @@version').fetchall()
        cursor.close()
        connection.close()

    # Since the connection may hang indefinitely (see comment on 'connection_timeout' in Focus DB definition)
    # perform the connection in a separate process. pyodbc acquires the GIL lock during connection, so signalling
    # or threading wouldn't work here.
    connection_process = multiprocessing.Process(target=attempt_connection)
    connection_process.start()
    connection_process.join(timeout)

    # If the connection attempt didn't finish, terminate it; it will get a non-zero exit code
    if connection_process.is_alive():
        # connection_process.terminate() sends SIGINT and pyodbc doesn't seem to respond to that while blocking. It
        # does respond to SIGHUP, so send that.
        os.kill(connection_process.pid, signal.SIGHUP)
        connection_process.join()

    focus_available = connection_process.exitcode == 0
    mc = pylibmc.Client(["memcached"], binary=True, behaviors={"tcp_nodelay": True, "ketama": True})
    mc.set("focus.connection", focus_available, time=cache_time)

if __name__ == '__main__':
    main()
