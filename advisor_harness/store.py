"""SQLite goal state, operation journal, and evidence graph."""

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .evidence import clean
from .policy import Blocked, Invalid


SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY, root TEXT NOT NULL, policy_digest TEXT NOT NULL,
    request TEXT NOT NULL, provider TEXT NOT NULL, mode TEXT NOT NULL,
    status TEXT NOT NULL, control TEXT NOT NULL DEFAULT 'run',
    initial TEXT NOT NULL, checkpoint TEXT NOT NULL, plan TEXT,
    result TEXT, supersedes TEXT REFERENCES goals(id),
    calls INTEGER NOT NULL DEFAULT 0, commands INTEGER NOT NULL DEFAULT 0,
    elapsed REAL NOT NULL DEFAULT 0, started REAL, heartbeat REAL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    goal TEXT REFERENCES goals(id), id TEXT, status TEXT NOT NULL,
    spec TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'work',
    repair INTEGER, PRIMARY KEY(goal,id)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, goal TEXT REFERENCES goals(id),
    task TEXT, kind TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS writes (
    id INTEGER PRIMARY KEY, goal TEXT REFERENCES goals(id), task TEXT,
    path TEXT NOT NULL, old_hash TEXT, new_hash TEXT NOT NULL,
    previous BLOB, status TEXT NOT NULL, repair INTEGER REFERENCES repairs(id)
);
CREATE TABLE IF NOT EXISTS repairs (
    id INTEGER PRIMARY KEY, goal TEXT REFERENCES goals(id), task TEXT,
    signature TEXT NOT NULL, check_id TEXT NOT NULL,
    failure INTEGER REFERENCES events(id), diagnosis TEXT NOT NULL,
    validation INTEGER REFERENCES events(id), reused INTEGER REFERENCES repairs(id),
    result TEXT NOT NULL, feature TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS repair_lookup ON repairs (signature, check_id, feature, id);
CREATE TABLE IF NOT EXISTS edges (
    goal TEXT REFERENCES goals(id), source TEXT, relation TEXT, target TEXT,
    PRIMARY KEY(goal,source,relation,target)
);
"""
TRANSITIONS = {
    "PENDING": {"RUNNING", "BLOCKED", "CANCELLED"},
    "RUNNING": {"BLOCKED", "FAILED", "VERIFIED", "CANCELLED"},
    "FAILED": {"RUNNING", "BLOCKED", "CANCELLED"},
    "BLOCKED": {"RUNNING", "CANCELLED"},
    "VERIFIED": {"COMPLETED", "BLOCKED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def unpack(row, fields):
    if row is None:
        return None
    value = dict(row)
    for field in fields:
        if value.get(field) is not None:
            value[field] = json.loads(value[field])
    return value


@contextmanager
def workspace_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            lock = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            unlock = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            lock = lambda: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            unlock = lambda: fcntl.flock(stream, fcntl.LOCK_UN)
        stream.seek(0)
        try:
            lock()
        except OSError as exc:
            raise Blocked("Workspace already has an active run") from exc
        try:
            yield
        finally:
            unlock()


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        self.conn = sqlite3.connect(self.path, timeout=5)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.conn.close()

    def new(self, root, policy_digest, request, provider, mode, snapshot, supersedes=None):
        goal = uuid.uuid4().hex
        data = json_text(snapshot)
        with self.conn:
            if supersedes:
                previous = self.goal(supersedes)
                if previous["root"] != str(root):
                    raise Invalid("Goal revision must use the same workspace")
                if previous["status"] in {"PENDING", "RUNNING", "FAILED", "BLOCKED"}:
                    self.transition("goals", supersedes, "CANCELLED")
                    for task in self.tasks(supersedes):
                        if task["status"] in {"PENDING", "RUNNING", "FAILED", "BLOCKED"}:
                            self.transition("tasks", supersedes, "CANCELLED", task["id"])
            self.conn.execute(
                "INSERT INTO goals(id,root,policy_digest,request,provider,mode,status,initial,checkpoint,"
                "supersedes,created) VALUES (?,?,?,?,?,?,'PENDING',?,?,?,?)",
                (goal, str(root), policy_digest, clean(request), provider, mode, data, data, supersedes, time.time()),
            )
            if supersedes:
                self.edge(goal, f"goal:{goal}", "supersedes", f"goal:{supersedes}")
        return goal

    def goal(self, goal):
        row = self.conn.execute("SELECT * FROM goals WHERE id=?", (goal,)).fetchone()
        if row is None:
            raise Invalid("Unknown goal id")
        return unpack(row, ("initial", "checkpoint", "plan", "result"))

    def tasks(self, goal):
        rows = self.conn.execute("SELECT * FROM tasks WHERE goal=? ORDER BY rowid", (goal,))
        return [unpack(row, ("spec",)) for row in rows]

    def transition(self, table, goal, to, task=None):
        if table == "goals":
            where, params = "id=?", (goal,)
        elif table == "tasks":
            where, params = "goal=? AND id=?", (goal, task)
        else:
            raise ValueError(table)
        current = self.conn.execute(f"SELECT status FROM {table} WHERE {where}", params).fetchone()[0]
        if to != current and to not in TRANSITIONS[current]:
            raise Invalid(f"Invalid status transition: {current} -> {to}")
        self.conn.execute(f"UPDATE {table} SET status=? WHERE {where}", (to, *params))

    def event(self, goal, task, kind, data):
        return self.conn.execute(
            "INSERT INTO events(goal,task,kind,data,created) VALUES (?,?,?,?,?)",
            (goal, task, kind, json_text(clean(data)), time.time()),
        ).lastrowid

    def events(self, goal):
        rows = self.conn.execute("SELECT * FROM events WHERE goal=? ORDER BY id", (goal,))
        return [unpack(row, ("data",)) for row in rows]

    def edge(self, goal, source, relation, target):
        self.conn.execute("INSERT OR IGNORE INTO edges VALUES (?,?,?,?)", (goal, source, relation, target))

    def experiences(self, signature, check_id, feature):
        rows = self.conn.execute(
            "SELECT id,goal,task,diagnosis,result,failure,validation,"
            "(SELECT count(*) FROM repairs later WHERE later.reused=repairs.id AND later.result='REGRESSION') "
            "AS regression_count FROM repairs "
            "WHERE signature=? AND check_id=? AND feature=? "
            "ORDER BY (result='VERIFIED') DESC,id DESC LIMIT 5",
            (signature, check_id, feature),
        )
        return [unpack(row, ("diagnosis",)) for row in rows]

    def report(self, goal):
        state = self.goal(goal)
        state.pop("policy_digest")
        state.pop("root")
        for attr in ("tasks", "events", "edges", "repairs"):
            if attr in {"tasks", "events"}:
                state[attr] = getattr(self, attr)(goal)
            else:
                state[attr] = [unpack(row, ("diagnosis",)) for row in self.conn.execute(
                    f"SELECT * FROM {attr} WHERE goal=? ORDER BY rowid", (goal,)
                )]
        return state
