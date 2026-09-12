"""Cursors for the app's tables. The host owns the connection and the transaction.

A copy of garageSim's server/db.py (the two apps are mounted the same way); kept in step by hand."""
from pymysql.cursors import DictCursor


def cursor(host):
    """A dict cursor on the host's connection, with @user_id set so the host's history triggers
    (if it generates any) record who did it."""
    conn = host.connect()
    cur = conn.cursor(DictCursor)
    cur.execute('SET @user_id = %s', (host.user(),))
    return conn, cur
