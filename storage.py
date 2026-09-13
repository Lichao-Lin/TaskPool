from __future__ import annotations

import math
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path


APP_NAME = "Termxk"
DATA_NAME = "TaskPool"
APP_VERSION = "3.0.0"
DEFAULT_ACCENT = "#50E3FF"
BG = "#000000"
PANEL = "#040608"
PANEL_2 = "#080C10"
TEXT = "#E6EDF3"
MUTED = "#8B9AAA"
DANGER = "#FF6B81"
WARNING = "#FFD166"


def app_config_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    path = Path(base) / DATA_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    """Return the user-selected storage directory, or the safe app default."""
    config_file = app_config_dir() / "config.json"
    if config_file.exists():
        try:
            configured = Path(json.loads(config_file.read_text(encoding="utf-8"))["data_dir"])
            configured.mkdir(parents=True, exist_ok=True)
            return configured
        except (OSError, ValueError, KeyError, TypeError):
            pass
    default = app_config_dir() / "data"
    default.mkdir(parents=True, exist_ok=True)
    return default


def save_data_dir(path: Path):
    config_file = app_config_dir() / "config.json"
    config_file.write_text(
        json.dumps({"data_dir": str(path.resolve())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class Storage:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else data_dir() / "taskpool.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    output TEXT NOT NULL,
                    deadline TEXT NOT NULL,
                    points INTEGER NOT NULL CHECK(points > 0),
                    status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo', 'done')),
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS rewards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    cost INTEGER NOT NULL CHECK(cost > 0),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount INTEGER NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('earn', 'spend')),
                    note TEXT NOT NULL,
                    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
                    reward_id INTEGER REFERENCES rewards(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_credit_per_task
                    ON ledger(task_id) WHERE kind = 'earn';
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

            reward_columns = {r[1] for r in conn.execute("PRAGMA table_info(rewards)")}
            if "archived_at" not in reward_columns:
                conn.execute("ALTER TABLE rewards ADD COLUMN archived_at TEXT")
                conn.execute("UPDATE rewards SET archived_at=(SELECT MAX(created_at) FROM ledger WHERE reward_id=rewards.id AND kind='spend') WHERE id IN (SELECT reward_id FROM ledger WHERE kind='spend')")
            columns = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
            if "parent_id" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN parent_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS routines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT NOT NULL CHECK(mode IN ('work', 'rest')),
                    content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS routine_checks (
                    routine_id INTEGER NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
                    day TEXT NOT NULL,
                    PRIMARY KEY(routine_id, day)
                );
            """)

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def add_task(self, content: str, output: str, deadline: str, points: int, parent_id: int | None = None):
        with self.connect() as conn:
            if parent_id is not None:
                parent = conn.execute("SELECT status FROM tasks WHERE id=?", (parent_id,)).fetchone()
                if not parent or parent[0] == 'done':
                    raise ValueError("请选择未完成的父任务")
            cursor = conn.execute(
                "INSERT INTO tasks(content, output, deadline, points, created_at, parent_id) VALUES(?,?,?,?,?,?)",
                (content.strip(), output.strip(), deadline, points, self._now(), parent_id),
            )
            return cursor.lastrowid

    def list_tasks(self):
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM tasks ORDER BY (status='done') ASC, deadline ASC, id DESC"
            ).fetchall()

    def complete_task(self, task_id: int) -> int:
        with self.connect() as conn:
            task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task:
                raise ValueError("任务不存在")
            if task["status"] == "done":
                raise ValueError("该任务已经完成")
            if conn.execute("SELECT 1 FROM tasks WHERE parent_id=? AND status='todo'", (task_id,)).fetchone():
                raise ValueError("请先完成这个任务下的子任务")
            now = self._now()
            conn.execute(
                "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
                (now, task_id),
            )
            conn.execute(
                "INSERT INTO ledger(amount, kind, note, task_id, created_at) VALUES(?, 'earn', ?, ?, ?)",
                (task["points"], f"完成任务：{task['content']}", task_id, now),
            )
            return int(task["points"])

    def delete_task(self, task_id: int):
        with self.connect() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def add_reward(self, name: str, description: str, cost: int):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO rewards(name, description, cost, created_at) VALUES(?,?,?,?)",
                (name.strip(), description.strip(), cost, self._now()),
            )

    def list_rewards(self):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM rewards ORDER BY cost ASC, id DESC").fetchall()

    def redeem_reward(self, reward_id: int) -> tuple[int, str]:
        with self.connect() as conn:
            reward = conn.execute("SELECT * FROM rewards WHERE id = ?", (reward_id,)).fetchone()
            if not reward:
                raise ValueError("奖励不存在")
            if reward['archived_at']:
                raise ValueError('奖励已兑换，请在日志查看')
            balance = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM ledger").fetchone()[0]
            if balance < reward["cost"]:
                raise ValueError(f"积分不足，还差 {reward['cost'] - balance} 分")
            conn.execute(
                "INSERT INTO ledger(amount, kind, note, reward_id, created_at) VALUES(?, 'spend', ?, ?, ?)",
                (-reward["cost"], f"兑换奖励：{reward['name']}", reward_id, self._now()),
            )
            conn.execute("UPDATE rewards SET archived_at=? WHERE id=?", (self._now(), reward_id))
            return int(reward["cost"]), str(reward["name"])

    def delete_reward(self, reward_id: int):
        with self.connect() as conn:
            conn.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))

    def balance(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COALESCE(SUM(amount), 0) FROM ledger").fetchone()[0])

    def stats(self):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) total, SUM(status='done') done FROM tasks"
            ).fetchone()
            spent = conn.execute(
                "SELECT COALESCE(-SUM(amount), 0) FROM ledger WHERE kind='spend'"
            ).fetchone()[0]
            return int(row["total"]), int(row["done"] or 0), int(spent)

    def get_setting(self, key: str, default: str) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return str(row[0]) if row else default

    def set_setting(self, key: str, value: str):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )


    def update_task(self, task_id, content, output, deadline, points):
        with self.connect() as conn:
            task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not task:
                raise ValueError("任务不存在")
            if task['status'] == 'done' and points != task['points']:
                raise ValueError("已完成任务的积分已入账，不能修改积分")
            conn.execute("UPDATE tasks SET content=?,output=?,deadline=?,points=? WHERE id=?",
                         (content.strip(), output.strip(), deadline, points, task_id))

    def update_reward(self, reward_id, name, description, cost):
        with self.connect() as conn:
            conn.execute("UPDATE rewards SET name=?,description=?,cost=? WHERE id=?",
                         (name.strip(), description.strip(), cost, reward_id))

    def list_routines(self, mode, day=None):
        day = day or datetime.now().date().isoformat()
        with self.connect() as conn:
            return conn.execute("""SELECT r.*,
                (SELECT COUNT(*) FROM routine_checks c WHERE c.routine_id=r.id) AS count,
                EXISTS(SELECT 1 FROM routine_checks c WHERE c.routine_id=r.id AND c.day=?) AS checked
                FROM routines r WHERE mode=? ORDER BY r.id""", (day, mode)).fetchall()

    def add_routine(self, mode, content):
        if not content.strip():
            raise ValueError("请填写每日安排")
        with self.connect() as conn:
            return conn.execute("INSERT INTO routines(mode,content) VALUES(?,?)", (mode, content.strip())).lastrowid

    def update_routine(self, routine_id, content):
        if not content.strip():
            raise ValueError("每日安排不能为空")
        with self.connect() as conn:
            conn.execute("UPDATE routines SET content=? WHERE id=?", (content.strip(), routine_id))

    def toggle_routine(self, routine_id, checked, day=None):
        day = day or datetime.now().date().isoformat()
        with self.connect() as conn:
            if checked:
                conn.execute("INSERT OR IGNORE INTO routine_checks VALUES(?,?)", (routine_id, day))
            else:
                conn.execute("DELETE FROM routine_checks WHERE routine_id=? AND day=?", (routine_id, day))

    def delete_routine(self, routine_id):
        with self.connect() as conn:
            conn.execute("DELETE FROM routines WHERE id=?", (routine_id,))

    def snapshot(self):
        with self.connect() as conn:
            return {table: [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
                    for table in ('tasks', 'rewards', 'ledger', 'routines', 'routine_checks')}

    def restore(self, snapshot):
        # One local undo stack: restore atomically, including credit and routine history.
        with self.connect() as conn:
            for table in ('routine_checks', 'ledger', 'tasks', 'rewards', 'routines'):
                conn.execute(f"DELETE FROM {table}")
            for table in ('tasks', 'rewards', 'ledger', 'routines', 'routine_checks'):
                rows = snapshot[table]
                if table == 'tasks':
                    rows = sorted(rows, key=lambda r: r['id'])
                for row in rows:
                    keys = ','.join(row)
                    conn.execute(f"INSERT INTO {table} ({keys}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))


def deadline_urgent(deadline, now=None):
    try:
        return datetime.strptime(deadline, "%Y-%m-%d %H:%M") <= (now or datetime.now()) + timedelta(days=2)
    except ValueError:
        return False


