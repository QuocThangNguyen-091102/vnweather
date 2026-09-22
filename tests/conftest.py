import logging

import pytest


class FakeCursor:
    """Cursor giả ghi lại mọi câu SQL, đủ dùng để kiểm thử logic mà không cần SQL Server."""

    def __init__(self, conn):
        self.conn = conn
        self.fast_executemany = False
        self._rows = []
        self.description = None

    def execute(self, sql, *params):
        self.conn.executed.append((" ".join(sql.split()), params))
        self._rows, self.description = [], None
        for marker, (columns, rows) in self.conn.frames.items():
            if marker in sql:
                self.description = [(c,) for c in columns]
                self._rows = list(rows)
                return self
        for marker, handler in self.conn.responders:
            if marker in sql:
                self._rows = handler(params)
                break
        return self

    def executemany(self, sql, rows):
        self.conn.many.append((" ".join(sql.split()), list(rows)))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    def __init__(self, responders=None):
        self.executed = []
        self.many = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.responders = responders or []
        self.frames = {}     # marker -> (danh sách cột, danh sách dòng), dùng cho các truy vấn trả về bảng

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True

    def sql_containing(self, text):
        return [(s, p) for s, p in self.executed if text in s]


@pytest.fixture
def fake_conn():
    return FakeConn()


@pytest.fixture(autouse=True)
def _clean_logging():
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_weather_platform", False):
            root.removeHandler(handler)
            handler.close()
