"""SQLite for the app's tables: the standalone app's default, and the tests' isolated database.

The data layer writes MariaDB SQL. On SQLite only the parameter marker, the row lock and the
session variable differ, and this cursor hides those. MariaDB behaviour (locks, a host's history
triggers) is still checked on a real MariaDB.

A copy of garageSim's server/sqlite.py apart from the schema file name; kept in step by hand."""
import re
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent / 'schema/schemaInput_Radio.sql'


class Cursor:
    def __init__(self, conn):
        self.cur = conn.cursor()

    def execute(self, sql, args=()):
        if sql.startswith('SET @user_id'):
            return
        return self.cur.execute(sql.replace('%s', '?').replace(' FOR UPDATE', ''), args)

    def fetchone(self):
        row = self.cur.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(row) for row in self.cur.fetchall()]

    def close(self):
        self.cur.close()

    @property
    def lastrowid(self):
        return self.cur.lastrowid


class Connection:
    """Looks enough like a pymysql connection for `server.db.cursor`: cursor(DictCursor), commit, rollback."""

    def __init__(self, path):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')

    def cursor(self, *_):
        return Cursor(self.conn)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def create_schema(path):
    """Apply the app's schema to a SQLite file (idempotent: the schema says IF NOT EXISTS)."""
    conn = sqlite3.connect(str(path))
    schema = re.sub(r'/\*.*?\*/', '', SCHEMA.read_text(), flags=re.S)
    schema = schema.replace('INT AUTO_INCREMENT PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT').replace('NOW()', 'CURRENT_TIMESTAMP')
    conn.executescript(schema)
    conn.close()
