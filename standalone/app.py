"""The log on app on its own: no host, no login, one nameless user, one unit.

    python3 standalone/app.py                      # SQLite in standalone/radio.sqlite, http://localhost:8091
    RADIO_DB=mysql://user:pw@host/radio python3 standalone/app.py
    docker compose -f standalone/docker-compose.yml up --build     # MariaDB + this, port 8091

This is the proof that the boundary holds: nothing here is quackit's."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flask import Flask, g, redirect                       # noqa: E402
from server import NullHost, mount                         # noqa: E402
from server import sqlite as lite                          # noqa: E402


def _mysql_connect(url):
    import pymysql
    m = re.match(r'mysql://([^:]+):([^@]*)@([^/:]+)(?::(\d+))?/(\w+)$', url)
    if not m:
        raise SystemExit('RADIO_DB must look like mysql://user:password@host[:port]/database')
    user, pw, host, port, db = m.groups()
    return lambda: pymysql.connect(host=host, port=int(port or 3306), user=user, password=pw, database=db, autocommit=False)


def _mysql_schema(connect):
    """Apply the schema statement by statement (all IF NOT EXISTS, so this is repeatable)."""
    sql = re.sub(r'/\*.*?\*/', '', lite.SCHEMA.read_text(), flags=re.S)
    sql = re.sub(r'--[^\n]*', '', sql)
    conn = connect()
    cur = conn.cursor()
    for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
        cur.execute(stmt)
    conn.commit()
    conn.close()


def create_app(db_url=None):
    db_url = db_url or os.environ.get('RADIO_DB') or 'sqlite:///' + str(Path(__file__).resolve().parent / 'radio.sqlite')
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'radio-standalone')
    if db_url.startswith('sqlite:///'):
        path = db_url[len('sqlite:///'):]
        lite.create_schema(path)
        def connect():
            if 'db' not in g:
                g.db = lite.Connection(path)
            return g.db
    elif db_url.startswith('mysql://'):
        raw = _mysql_connect(db_url)
        _mysql_schema(raw)
        def connect():
            if 'db' not in g:
                g.db = raw()
            return g.db
    else:
        raise SystemExit('RADIO_DB must start with sqlite:/// or mysql://')

    @app.teardown_appcontext
    def close(_):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    mount(app, NullHost(connect))
    app.add_url_rule('/', 'home', lambda: redirect('/logons'))
    return app


if __name__ == '__main__':
    create_app().run(host=os.environ.get('HOST', '0.0.0.0'), port=int(os.environ.get('PORT', '8091')), debug=False)
