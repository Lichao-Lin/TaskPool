from __future__ import annotations

import math
import json
import os
import sqlite3
import sys
import tkinter as tk
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import ttk


APP_NAME = "TaskPool"
APP_VERSION = "2.0.1"
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
    path = Path(base) / APP_NAME
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
            balance = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM ledger").fetchone()[0]
            if balance < reward["cost"]:
                raise ValueError(f"积分不足，还差 {reward['cost'] - balance} 分")
            conn.execute(
                "INSERT INTO ledger(amount, kind, note, reward_id, created_at) VALUES(?, 'spend', ?, ?, ?)",
                (-reward["cost"], f"兑换奖励：{reward['name']}", reward_id, self._now()),
            )
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


class TaskPoolApp(tk.Tk):
    def __init__(self, storage=None):
        super().__init__()
        self.db = storage or Storage()
        self.accent = self.db.get_setting('accent', DEFAULT_ACCENT)
        self.bg = self.db.get_setting('background', BG)
        self.text = self.db.get_setting('text', TEXT)
        self.edit_task_id = self.parent_id = self.edit_reward_id = self.selected_reward = None
        self.reward_page = 0
        self.undo_stack = []
        self.day = datetime.now().date().isoformat()
        self.mode = tk.StringVar(value=self.db.get_setting('routine_mode', 'work'))
        self.title(f'TaskPool / 全息任务控制台 · v{APP_VERSION}')
        self.geometry('1480x900')
        self.minsize(1180, 740)
        self.configure(bg=self.bg)
        self._build_style()
        self.backdrop = tk.Canvas(self, bg=self.bg, highlightthickness=0)
        self.backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        self.background_image = None
        self._build_ui()
        self.load_background(self.db.get_setting('background_image', ''), quiet=True)
        self.bind('<Configure>', self._resize_background)
        self.bind('<Control-z>', lambda e: self.undo())
        self.refresh()
        self.after(1000, self.tick)

    def _build_style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=self.bg, foreground=self.text, font=('Microsoft YaHei UI', 10))
        s.configure('TFrame', background=self.bg)
        s.configure('Panel.TFrame', background=PANEL)
        s.configure('TLabel', background=self.bg, foreground=self.text)
        s.configure('Panel.TLabel', background=PANEL, foreground=self.text)
        s.configure('Muted.TLabel', background=PANEL, foreground=MUTED, font=('Microsoft YaHei UI', 9))
        s.configure('TEntry', fieldbackground=PANEL_2, foreground=self.text, insertcolor=self.text, padding=5,
                    bordercolor='#244552', lightcolor='#244552', darkcolor='#244552')
        s.configure('TButton', background=PANEL_2, foreground=self.text, padding=(9, 5), borderwidth=0)
        s.map('TButton', background=[('active', '#23404C')])
        s.configure('Accent.TButton', background=self.accent, foreground='#001018')
        s.map('Accent.TButton', background=[('active', '#ACF1FF')], foreground=[('active', '#001018')])
        s.configure('TRadiobutton', background=PANEL, foreground=self.text, padding=4)
        s.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=self.text,
                    bordercolor='#15313D', lightcolor='#15313D', darkcolor='#15313D', rowheight=42, borderwidth=0, font=('Microsoft YaHei UI', 10))
        s.configure('Treeview.Heading', background=PANEL_2, foreground=self.accent, padding=6, bordercolor='#15313D', lightcolor='#15313D', darkcolor='#15313D')
        s.configure('Vertical.TScrollbar', background='#10202A', troughcolor=PANEL, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL, arrowcolor=MUTED)
        s.map('Treeview', background=[('selected', '#153847')])

    def panel(self, parent, title, subtitle):
        frame = ttk.Frame(parent, style='Panel.TFrame', padding=12)
        ttk.Label(frame, text=title, style='Panel.TLabel', foreground=self.accent,
                  font=('Consolas', 12, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=subtitle, style='Muted.TLabel').pack(anchor='w', pady=(3, 10))
        return frame

    def _build_ui(self):
        self.header = ttk.Frame(self, padding=(22, 16))
        self.header.pack(fill='x', padx=16, pady=(14, 0))
        ttk.Label(self.header, text='◉  TASK / POOL', foreground=self.accent,
                  font=('Consolas', 24, 'bold')).pack(side='left')
        ttk.Label(self.header, text='PERSONAL OPERATING SYSTEM  /  本地控制台', foreground=MUTED,
                  font=('Consolas', 10)).pack(side='left', padx=20)
        self.settings_button = ttk.Button(self.header, text='界面与存储设置', command=self.toggle_settings)
        self.settings_button.pack(side='right')
        self.settings_panel = ttk.Frame(self, padding=12, style='Panel.TFrame')
        self._build_settings()
        body = ttk.Frame(self, padding=6)
        self.body = body
        body.pack(fill='both', expand=True, padx=16, pady=8)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)
        stat = ttk.Frame(body, padding=(12, 8), style='Panel.TFrame')
        stat.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.balance_label = ttk.Label(stat, foreground=self.accent, style='Panel.TLabel', font=('Consolas', 25, 'bold'))
        self.balance_label.pack(side='left')
        self.stats_label = ttk.Label(stat, style='Muted.TLabel')
        self.stats_label.pack(side='left', padx=22)
        self.clock_label = ttk.Label(stat, style='Muted.TLabel')
        self.clock_label.pack(side='right')
        self.dashboard = ttk.Frame(body)
        self.dashboard.grid(row=1, column=0, sticky='nsew')
        for col, weight in enumerate((32, 43, 25)):
            self.dashboard.columnconfigure(col, weight=weight, uniform='columns')
        self.dashboard.rowconfigure(0, weight=1)
        self.reward_panel = self.panel(self.dashboard, '01 / REWARD ORBIT', '奖励轨道 · 点击文字查看与兑换')
        self.task_panel = self.panel(self.dashboard, '02 / MISSION CONTROL', '任务与子任务 · 48 小时内到期自动标红')
        self.routine_panel = self.panel(self.dashboard, '03 / DAILY ROUTINE', '每日刷新勾选 · 保留累计次数')
        for i, panel in enumerate((self.reward_panel, self.task_panel, self.routine_panel)):
            panel.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 5, 0 if i == 2 else 5))
        self._build_rewards()
        self._build_tasks()
        self._build_routines()
        self.forms = ttk.Frame(body)
        self.forms.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        for i in range(2):
            self.forms.columnconfigure(i, weight=1, uniform='forms')
        self._build_forms()
        footer = ttk.Frame(self, padding=(22, 0, 22, 10))
        footer.pack(side='bottom', fill='x', before=body)
        self.status_label = ttk.Label(footer, text='系统就绪 · 所有更改自动保存在本地', foreground=self.accent)
        self.status_label.pack(side='left')
        self.undo_button = ttk.Button(footer, text='撤销上一步  Ctrl+Z', command=self.undo, state='disabled')
        self.undo_button.pack(side='right')

    def _build_tasks(self):
        bar = ttk.Frame(self.task_panel, style='Panel.TFrame')
        bar.pack(fill='x', pady=(0, 7))
        for label, fn in [('✓ 完成', self.complete_selected), ('编辑', self.edit_task), ('+ 子任务', self.add_subtask), ('删除', self.delete_task)]:
            ttk.Button(bar, text=label, command=fn).pack(side='left', padx=(0, 4))
        area = ttk.Frame(self.task_panel, style='Panel.TFrame')
        area.pack(fill='both', expand=True)
        self.task_tree = ttk.Treeview(area, columns=('deadline', 'points'), show='tree headings', selectmode='browse')
        self.task_tree.heading('#0', text='任务 / 子任务')
        self.task_tree.column('#0', width=260, minwidth=160)
        self.task_tree.heading('deadline', text='截止时间')
        self.task_tree.column('deadline', width=128, minwidth=116, stretch=False)
        self.task_tree.heading('points', text='积分')
        self.task_tree.column('points', width=48, minwidth=42, stretch=False, anchor='center')
        sc = ttk.Scrollbar(area, orient='vertical', command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=sc.set)
        sc.pack(side='right', fill='y')
        self.task_tree.pack(fill='both', expand=True)
        self.task_tree.tag_configure('done', foreground=MUTED)
        self.task_tree.tag_configure('urgent', foreground=DANGER)
        self.task_tree.bind('<Double-1>', lambda e: self.edit_task())
        self.task_tree.bind('<<TreeviewSelect>>', self.task_detail)
        self.task_detail_label = ttk.Label(self.task_panel, text='选择任务查看产出；双击直接编辑', style='Muted.TLabel', wraplength=420)
        self.task_detail_label.pack(fill='x', pady=(8, 0))

    def _build_rewards(self):
        self.orbit = tk.Canvas(self.reward_panel, bg=PANEL, highlightthickness=0, height=280)
        self.orbit.pack(fill='both', expand=True)
        self.orbit.bind('<Configure>', lambda e: self.draw_orbit())
        nav = ttk.Frame(self.reward_panel, style='Panel.TFrame')
        nav.pack(fill='x')
        ttk.Button(nav, text='‹', command=lambda: self.page_rewards(-1)).pack(side='left')
        self.page_label = ttk.Label(nav, style='Muted.TLabel', anchor='center')
        self.page_label.pack(side='left', fill='x', expand=True)
        ttk.Button(nav, text='›', command=lambda: self.page_rewards(1)).pack(side='right')
        self.reward_detail_label = ttk.Label(self.reward_panel, text='选择奖励查看详情与兑换' , style='Muted.TLabel', wraplength=330)
        self.reward_detail_label.pack(fill='x', pady=8)
        bar = ttk.Frame(self.reward_panel, style='Panel.TFrame')
        bar.pack(fill='x')
        for title, fn in [('兑换', self.redeem_selected), ('编辑', self.edit_reward), ('删除', self.delete_reward)]:
            ttk.Button(bar, text=title, command=fn).pack(side='left', padx=(0, 6))

    def draw_orbit(self):
        c = self.orbit
        c.delete('all')
        w, h = max(c.winfo_width(), 260), max(c.winfo_height(), 220)
        cx, cy = w / 2, h / 2
        rx = ry = min(w, h) * .165
        for scale, color in ((1.15, '#173C48'), (1, self.accent), (.84, '#245B6A'), (.58, '#142F3B')):
            c.create_oval(cx-rx*scale, cy-ry*scale, cx+rx*scale, cy+ry*scale, outline=color, width=1)
        c.create_arc(cx-rx*1.05, cy-ry*1.05, cx+rx*1.05, cy+ry*1.05, start=getattr(self, 'scan_angle', 0), extent=46, style='arc', outline='#2595AD', width=2, tags='scan')
        for angle in range(0, 360, 10):
            a = math.radians(angle)
            c.create_line(cx+rx*1.19*math.cos(a), cy+ry*1.19*math.sin(a), cx+rx*1.23*math.cos(a), cy+ry*1.23*math.sin(a), fill='#285565')
        c.create_line(cx-25, cy, cx+25, cy, fill='#245B6A')
        c.create_text(cx, cy-12, text=str(self.db.balance()), fill=self.accent, font=('Consolas', 22, 'bold'))
        c.create_text(cx, cy+17, text='PTS', fill=MUTED, font=('Consolas', 8))
        rewards = self.db.list_rewards()
        pages = max(1, math.ceil(len(rewards)/12))
        self.reward_page = min(self.reward_page, pages-1)
        self.page_label.configure(text=f'{self.reward_page+1} / {pages}  ·  {len(rewards)} 份奖励')
        for i, reward in enumerate(rewards[self.reward_page*12:self.reward_page*12+12]):
            # Consecutive slots deliberately leave the unused arc empty.
            degrees = -112+i*24
            angle = math.radians(degrees)
            ux, uy = math.cos(angle), math.sin(angle)
            vx, vy = -uy, ux
            inner = min(w, h)*.205
            radial_width = min(w, h)*.28
            x, y = cx+inner*ux, cy+inner*uy
            tag = f'reward{reward["id"]}'
            selected = reward['id'] == self.selected_reward
            color = self.accent if self.db.balance() >= reward['cost'] else '#819BA6'
            from tkinter.font import Font
            font = Font(family='Microsoft YaHei UI', size=8)
            name = reward['name']
            if font.measure(name) > radial_width:
                while name and font.measure(name+'…') > radial_width:
                    name = name[:-1]
                name += '…'
            c.create_text(x-7*vx, y-7*vy, text=name, fill=self.accent if selected else self.text,
                          font=font, anchor='w', angle=-degrees, tags=tag)
            c.create_text(x+8*vx, y+8*vy, text=f'{reward["cost"]} PTS', fill=color,
                          font=('Consolas', 7), anchor='w', angle=-degrees, tags=tag)
            c.tag_bind(tag, '<Button-1>', lambda e, rid=reward['id']: self.select_reward(rid))
        if not rewards:
            c.create_text(cx, h-14, text='从下方输入奖励，建立你的奖励轨道', fill=MUTED, font=('Microsoft YaHei UI', 9))

    def page_rewards(self, delta):
        pages = max(1, math.ceil(len(self.db.list_rewards())/12))
        self.reward_page = (self.reward_page+delta) % pages
        self.draw_orbit()

    def select_reward(self, rid):
        self.selected_reward = rid
        r = next((r for r in self.db.list_rewards() if r['id']==rid), None)
        if r:
            self.reward_detail_label.configure(text=f'{r["name"]} · {r["cost"]} 积分\n{r["description"] or "无附加说明"}')
        self.draw_orbit()
    def _build_routines(self):
        modes = ttk.Frame(self.routine_panel, style='Panel.TFrame')
        modes.pack(fill='x')
        for title, value in [('工作日', 'work'), ('休息日', 'rest')]:
            ttk.Radiobutton(modes, text=title, value=value, variable=self.mode, command=self.switch_mode).pack(side='left')
        self.routine_summary = ttk.Label(self.routine_panel, style='Muted.TLabel')
        self.routine_summary.pack(anchor='w', pady=8)
        area = ttk.Frame(self.routine_panel, style='Panel.TFrame')
        area.pack(fill='both', expand=True)
        self.routine_canvas = tk.Canvas(area, bg=PANEL, highlightthickness=0, width=240, height=160)
        scroll = ttk.Scrollbar(area, orient='vertical', command=self.routine_canvas.yview)
        self.routine_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.routine_canvas.pack(side='left', fill='both', expand=True)
        self.routine_rows = ttk.Frame(self.routine_canvas, style='Panel.TFrame')
        self.routine_window = self.routine_canvas.create_window(0, 0, anchor='nw', window=self.routine_rows)
        self.routine_rows.bind('<Configure>', lambda e: self.routine_canvas.configure(scrollregion=self.routine_canvas.bbox('all')))
        self.routine_canvas.bind('<Configure>', lambda e: self.routine_canvas.itemconfigure(self.routine_window, width=e.width))
        entrybar = ttk.Frame(self.routine_panel, style='Panel.TFrame')
        entrybar.pack(fill='x', pady=(8, 0))
        self.routine_entry = ttk.Entry(entrybar)
        self.routine_entry.pack(side='left', fill='x', expand=True)
        self.routine_entry.bind('<Return>', lambda e: self.add_routine())
        ttk.Button(entrybar, text='+ 添加', command=self.add_routine).pack(side='right', padx=(5, 0))

    def refresh_routines(self):
        self._rebuilding_routines = True
        for child in self.routine_rows.winfo_children():
            child.destroy()
        routines = self.db.list_routines(self.mode.get())
        self.routine_summary.configure(text=f'{self.day}   ·   今日 {sum(r["checked"] for r in routines)}/{len(routines)}')
        for r in routines:
            row = ttk.Frame(self.routine_rows, style='Panel.TFrame', padding=(0, 5))
            row.pack(fill='x')
            ttk.Button(row, text='☑' if r['checked'] else '☐', width=2,
                       command=lambda rid=r['id'], checked=r['checked']: self.check_routine(rid, not checked)).pack(side='left')
            entry = ttk.Entry(row, width=12)
            entry.insert(0, r['content'])
            entry.pack(side='left', fill='x', expand=True, padx=4)
            entry.bind('<Return>', lambda e, rid=r['id'], en=entry: self.save_routine(rid, en))
            entry.bind('<KeyRelease>', lambda e, rid=r['id'], en=entry: self.save_routine(rid, en))
            entry.bind('<FocusOut>', lambda e, rid=r['id'], en=entry: self.save_routine(rid, en))
            ttk.Label(row, text=f'{r["count"]} 次', style='Muted.TLabel').pack(side='left')
            ttk.Button(row, text='×', width=2, command=lambda rid=r['id']: self.remove_routine(rid)).pack(side='right')
        if not routines:
            ttk.Label(self.routine_rows, text='在下方写下每天想做的事。\n例如：阅读 20 分钟、运动。', style='Muted.TLabel').pack(anchor='w', pady=24)
        self._rebuilding_routines = False

    def switch_mode(self):
        self.db.set_setting('routine_mode', self.mode.get())
        self.refresh_routines()

    def add_routine(self):
        self.change(lambda: self.db.add_routine(self.mode.get(), self.routine_entry.get()), '每日安排已添加', routines=True)
        if self.last_ok:
            self.routine_entry.delete(0, 'end')

    def save_routine(self, rid, entry):
        if self._rebuilding_routines or not entry.winfo_exists():
            return
        current = next((r for r in self.db.list_routines(self.mode.get()) if r['id']==rid), None)
        if current and current['content'] != entry.get().strip():
            self.change(lambda: self.db.update_routine(rid, entry.get()), '每日安排已保存', refresh=False)

    def check_routine(self, rid, checked):
        self.change(lambda: self.db.toggle_routine(rid, checked), '今日完成次数已更新', routines=True)

    def remove_routine(self, rid):
        self.change(lambda: self.db.delete_routine(rid), '每日安排已删除，可撤销', routines=True)

    def _build_forms(self):
        reward = self.panel(self.forms, 'REWARD INPUT / 奖励输入', '奖励名称、说明与兑换积分')
        task = self.panel(self.forms, 'TASK INPUT / 任务输入', '任务内容、产出、截止时间与积分')
        reward.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        task.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        self.reward_form_title = reward.winfo_children()[0]
        self.task_form_title = task.winfo_children()[0]
        self.reward_name, self.reward_description, self.reward_cost = self.fields_row(reward, [('名称', '', 18), ('说明', '', 22), ('积分', '50', 6)])
        self.task_content, self.task_output = self.fields_row(task, [('任务', '', 22), ('产出', '', 22)])
        self.task_deadline, self.task_points = self.fields_row(task, [('截止', datetime.now().strftime('%Y-%m-%d 23:59'), 22), ('积分', '10', 6)])
        rbar = ttk.Frame(reward, style='Panel.TFrame')
        rbar.pack(fill='x', pady=(8, 0))
        self.reward_submit = ttk.Button(rbar, text='+ 添加奖励', style='Accent.TButton', command=self.add_reward)
        self.reward_submit.pack(side='left')
        ttk.Button(rbar, text='清空 / 取消编辑', command=self.reset_reward_form).pack(side='left', padx=8)
        tbar = ttk.Frame(task, style='Panel.TFrame')
        tbar.pack(fill='x', pady=(8, 0))
        self.task_submit = ttk.Button(tbar, text='+ 添加任务', style='Accent.TButton', command=self.add_task)
        self.task_submit.pack(side='left')
        ttk.Button(tbar, text='清空 / 取消编辑', command=self.reset_task_form).pack(side='left', padx=8)
        self.task_content.bind('<Return>', lambda e: self.add_task())
        self.reward_name.bind('<Return>', lambda e: self.add_reward())

    def fields_row(self, panel, fields):
        row = ttk.Frame(panel, style='Panel.TFrame')
        row.pack(fill='x', pady=3)
        entries = []
        for label, default, width in fields:
            ttk.Label(row, text=label, style='Muted.TLabel').pack(side='left', padx=(0, 5))
            entry = ttk.Entry(row, width=width)
            entry.insert(0, default)
            entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
            entries.append(entry)
        return entries

    @staticmethod
    def put(entry, value):
        entry.delete(0, 'end')
        entry.insert(0, str(value))

    def reset_task_form(self):
        self.edit_task_id = self.parent_id = None
        self.task_form_title.configure(text='TASK INPUT / 任务输入')
        self.task_submit.configure(text='+ 添加任务')
        self.put(self.task_content, '')
        self.put(self.task_output, '')

    def reset_reward_form(self):
        self.edit_reward_id = None
        self.reward_form_title.configure(text='REWARD INPUT / 奖励输入')
        self.reward_submit.configure(text='+ 添加奖励')
        self.put(self.reward_name, '')
        self.put(self.reward_description, '')

    def selected_task(self):
        selection = self.task_tree.selection()
        if not selection:
            raise ValueError('请先在列表中选择任务')
        return int(selection[0])

    def task_detail(self, event=None):
        if self.task_tree.selection():
            rid = int(self.task_tree.selection()[0])
            r = next((r for r in self.db.list_tasks() if r['id']==rid), None)
            if r:
                self.task_detail_label.configure(text=f'{r["content"]}\n产出：{r["output"]}')

    def edit_task(self):
        try:
            rid = self.selected_task()
            r = next(r for r in self.db.list_tasks() if r['id']==rid)
            self.reset_task_form()
            self.edit_task_id = rid
            for entry, key in ((self.task_content, 'content'), (self.task_output, 'output'), (self.task_deadline, 'deadline'), (self.task_points, 'points')):
                self.put(entry, r[key])
            self.task_form_title.configure(text=f'EDIT / 编辑任务 #{rid}')
            self.task_submit.configure(text='保存修改')
            self.task_content.focus_set()
        except ValueError as e:
            self.show_status(str(e), True)

    def add_subtask(self):
        try:
            rid = self.selected_task()
            parent = next(r for r in self.db.list_tasks() if r['id']==rid)
            if parent['status']=='done':
                raise ValueError('已完成任务不能再添加子任务')
            self.reset_task_form()
            self.parent_id = rid
            self.put(self.task_deadline, parent['deadline'])
            self.task_form_title.configure(text=f'SUBTASK / 添加到任务 #{rid}')
            self.task_submit.configure(text='+ 添加子任务')
            self.task_content.focus_set()
        except ValueError as e:
            self.show_status(str(e), True)

    @staticmethod
    def positive(value):
        try:
            n = int(value)
            if n > 0:
                return n
        except ValueError:
            pass
        raise ValueError('积分必须是大于 0 的整数')

    def add_task(self):
        def operation():
            content, output = self.task_content.get().strip(), self.task_output.get().strip()
            if not content or not output:
                raise ValueError('请填写任务内容和产出要求')
            deadline = self.task_deadline.get().strip()
            try:
                deadline = datetime.strptime(deadline, '%Y-%m-%d %H:%M').strftime('%Y-%m-%d %H:%M')
            except ValueError:
                raise ValueError('截止时间格式：2026-09-09 18:00')
            points = self.positive(self.task_points.get())
            if self.edit_task_id is not None:
                self.db.update_task(self.edit_task_id, content, output, deadline, points)
            else:
                self.db.add_task(content, output, deadline, points, self.parent_id)
        self.change(operation, '任务已保存')
        if self.last_ok:
            self.reset_task_form()

    def complete_selected(self):
        self.change(lambda: self.db.complete_task(self.selected_task()), '任务达成，积分已到账')

    def delete_task(self):
        self.change(lambda: self.db.delete_task(self.selected_task()), '任务及子任务已删除，关联积分已撤销 · 可撤销')
        if self.last_ok:
            self.reset_task_form()

    def edit_reward(self):
        r = next((r for r in self.db.list_rewards() if r['id']==self.selected_reward), None)
        if not r:
            return self.show_status('请先点击奖励轨道上的文字', True)
        self.edit_reward_id = r['id']
        for entry, key in ((self.reward_name, 'name'), (self.reward_description, 'description'), (self.reward_cost, 'cost')):
            self.put(entry, r[key])
        self.reward_form_title.configure(text=f'EDIT / 编辑奖励 #{r["id"]}')
        self.reward_submit.configure(text='保存修改')
        self.reward_name.focus_set()

    def add_reward(self):
        def operation():
            name = self.reward_name.get().strip()
            if not name:
                raise ValueError('请填写奖励名称')
            cost = self.positive(self.reward_cost.get())
            if self.edit_reward_id is None:
                self.db.add_reward(name, self.reward_description.get(), cost)
            else:
                self.db.update_reward(self.edit_reward_id, name, self.reward_description.get(), cost)
        self.change(operation, '奖励已保存')
        if self.last_ok:
            self.reset_reward_form()

    def reward_id(self):
        if self.selected_reward is None:
            raise ValueError('请先点击奖励轨道上的文字')
        return self.selected_reward

    def redeem_selected(self):
        self.change(lambda: self.db.redeem_reward(self.reward_id()), '奖励已兑换，积分已扣除 · 可撤销')

    def delete_reward(self):
        self.change(lambda: self.db.delete_reward(self.reward_id()), '奖励已删除，历史兑换记录保留 · 可撤销')
        if self.last_ok:
            self.selected_reward = None
            self.reset_reward_form()
            self.reward_detail_label.configure(text='选择奖励查看详情')
    def change(self, operation, message, refresh=True, routines=False):
        self.last_ok = False
        try:
            snapshot = self.db.snapshot()
            operation()
            self.undo_stack.append((snapshot, self.db.snapshot()))
            self.undo_stack = self.undo_stack[-30:]
            self.undo_button.configure(state='normal')
            self.last_ok = True
            if routines:
                self.refresh_routines()
            elif refresh:
                self.refresh()
            self.show_status(message)
        except (ValueError, sqlite3.Error, OSError) as e:
            self.show_status(str(e), True)

    def undo(self):
        if not self.undo_stack:
            return
        try:
            before, expected = self.undo_stack[-1]
            if self.db.snapshot() != expected:
                self.undo_stack.clear()
                self.undo_button.configure(state='disabled')
                self.refresh()
                return self.show_status('数据已在其他窗口更新，已刷新；旧撤销记录已清空', True)
            self.db.restore(before)
            self.undo_stack.pop()
            self.reset_task_form()
            self.reset_reward_form()
            self.refresh()
            self.undo_button.configure(state='normal' if self.undo_stack else 'disabled')
            self.show_status('已撤销上一步，数据与积分已恢复')
        except sqlite3.Error as e:
            self.show_status(str(e), True)

    def show_status(self, message, error=False):
        self.status_label.configure(text=message, foreground=DANGER if error else self.accent)

    def refresh(self):
        selection = self.task_tree.selection()
        opened = {str(r['id']): self.task_tree.item(str(r['id']), 'open') for r in self.db.list_tasks() if self.task_tree.exists(str(r['id']))}
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)
        tasks = self.db.list_tasks()
        by_parent = {}
        for r in tasks:
            by_parent.setdefault(r['parent_id'], []).append(r)
        def insert(parent_id=None):
            for r in by_parent.get(parent_id, []):
                done = r['status']=='done'
                urgent = not done and deadline_urgent(r['deadline'])
                title = ('✓ ' if done else '◇ ') + r['content']
                self.task_tree.insert('' if parent_id is None else str(parent_id), 'end', iid=str(r['id']), text=title,
                    values=(r['deadline'], r['points']), open=opened.get(str(r['id']), True),
                    tags=('done',) if done else ('urgent',) if urgent else ())
                insert(r['id'])
        insert()
        if selection and self.task_tree.exists(selection[0]):
            self.task_tree.selection_set(selection[0])
        total, done, spent = self.db.stats()
        self.balance_label.configure(text=f'{self.db.balance():04d} PTS')
        urgent = sum(r['status']=='todo' and deadline_urgent(r['deadline']) for r in tasks)
        self.stats_label.configure(text=f'任务 {done}/{total}   /   临期 {urgent}   /   已兑换 {spent} PTS')
        self.draw_orbit()
        self.refresh_routines()
        if self.selected_reward is not None:
            self.select_reward(self.selected_reward)

    def tick(self):
        now = datetime.now()
        self.clock_label.configure(text=now.strftime('%Y.%m.%d   %H:%M:%S')+'  /  LOCAL')
        if self.day != now.date().isoformat():
            self.day = now.date().isoformat()
            self.undo_stack.clear()
            self.undo_button.configure(state='disabled')
            self.refresh()
        for r in self.db.list_tasks():
            if self.task_tree.exists(str(r['id'])):
                self.task_tree.item(str(r['id']), tags=('done',) if r['status']=='done' else ('urgent',) if deadline_urgent(r['deadline'], now) else ())
        self.scan_angle = (getattr(self, 'scan_angle', 0)+9) % 360
        self.orbit.itemconfigure('scan', start=self.scan_angle)
        self._tick_job = self.after(1000, self.tick)

    def _build_settings(self):
        row = ttk.Frame(self.settings_panel, style='Panel.TFrame')
        row.pack(fill='x')
        self.setting_entries = {}
        for key, label, value in [('background', '背景色', self.bg), ('text', '文字色', self.text), ('accent', '强调色', self.accent)]:
            ttk.Label(row, text=label+' #HEX', style='Muted.TLabel').pack(side='left', padx=5)
            en = ttk.Entry(row, width=9)
            en.insert(0, value)
            en.pack(side='left')
            self.setting_entries[key] = en
        ttk.Button(row, text='应用颜色', command=self.apply_colors).pack(side='left', padx=8)
        for title, bg, fg, accent in [('冰蓝', '#000000', '#E6EDF3', '#50E3FF'), ('琥珀', '#080503', '#FFF2D6', '#FFBE55'), ('紫光', '#080510', '#EEE7FF', '#B398FF')]:
            ttk.Button(row, text=title, command=lambda b=bg, f=fg, a=accent: self.preset(b, f, a)).pack(side='left', padx=3)
        choices = [
            ('background', '背景', [('纯黑','#000000'),('深空','#020508'),('墨蓝','#030911'),('暗紫','#080410'),('炭灰','#101010')]),
            ('text', '文字', [('霜白','#E6EDF3'),('银灰','#B5C4CF'),('冰蓝','#9CEAFF'),('青绿','#91F7D0'),('琥珀','#FFD08A'),('淡紫','#CDBAFF'),('玫红','#FFB1CE')]),
            ('accent', '光效', [('冰蓝','#50E3FF'),('青绿','#52FFC2'),('琥珀','#FFBE55'),('紫光','#B398FF'),('玫红','#FF77BB'),('纯白','#FFFFFF')]),
        ]
        for key, label, colors in choices:
            palette = ttk.Frame(self.settings_panel, style='Panel.TFrame')
            palette.pack(fill='x', pady=(5, 0))
            ttk.Label(palette, text=label+'颜色', style='Muted.TLabel', width=9).pack(side='left')
            for name, color in colors:
                button = tk.Button(palette, text='● '+name, bg=color if key=='background' else PANEL_2,
                    fg='#E6EDF3' if key=='background' else color, activebackground='#15313D',
                    activeforeground='#FFFFFF', relief='flat', bd=0, padx=10, pady=2,
                    highlightthickness=1, highlightbackground='#1D3340', cursor='hand2',
                    font=('Microsoft YaHei UI', 9), command=lambda k=key, c=color: self.select_color(k,c))
                button.pack(side='left', padx=(0, 5))
        line = ttk.Frame(self.settings_panel, style='Panel.TFrame')
        line.pack(fill='x', pady=(8, 0))
        ttk.Label(line, text='背景图片路径', style='Muted.TLabel').pack(side='left')
        self.image_path = ttk.Entry(line)
        self.image_path.insert(0, self.db.get_setting('background_image', ''))
        self.image_path.pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(line, text='应用图片', command=lambda: self.load_background(self.image_path.get())).pack(side='left')
        ttk.Button(line, text='清除图片', command=lambda: self.load_background('')).pack(side='left', padx=5)
        line2 = ttk.Frame(self.settings_panel, style='Panel.TFrame')
        line2.pack(fill='x', pady=(8, 0))
        ttk.Label(line2, text='数据文件夹', style='Muted.TLabel').pack(side='left')
        self.data_path_entry = ttk.Entry(line2)
        self.data_path_entry.insert(0, str(self.db.path.parent))
        self.data_path_entry.pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(line2, text='迁移 / 切换', command=self.choose_data_path).pack(side='left')
        ttk.Label(line2, text='已有数据直接读取；空目录复制当前数据', style='Muted.TLabel').pack(side='left', padx=8)

    def toggle_settings(self):
        if self.settings_panel.winfo_manager():
            self.settings_panel.pack_forget()
            self.body.pack(after=self.header, fill='both', expand=True, padx=16, pady=8)
            self.settings_button.configure(text='界面与存储设置')
        else:
            self.body.pack_forget()
            self.settings_panel.pack(after=self.header, fill='both', expand=True, padx=22, pady=10)
            self.settings_button.configure(text='返回任务控制台')

    def select_color(self, key, color):
        self.put(self.setting_entries[key], color)
        self.apply_colors()

    def preset(self, bg, text, accent):
        for key, value in [('background', bg), ('text', text), ('accent', accent)]:
            self.put(self.setting_entries[key], value)
        self.apply_colors()

    def apply_colors(self):
        import re
        values = {k: e.get().strip() for k, e in self.setting_entries.items()}
        if not all(re.fullmatch(r'#[0-9a-fA-F]{6}', value) for value in values.values()):
            return self.show_status('颜色格式为 #RRGGBB，例如 #50E3FF', True)
        for key, value in values.items():
            self.db.set_setting(key, value)
        old_accent = self.accent
        self.bg, self.text, self.accent = values['background'], values['text'], values['accent']
        self._build_style()
        self.configure(bg=self.bg)
        self.backdrop.configure(bg=self.bg)
        def recolor(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Label) and str(child.cget('foreground')) == old_accent:
                    child.configure(foreground=self.accent)
                recolor(child)
        recolor(self)
        self.balance_label.configure(foreground=self.accent)
        self.draw_orbit()
        self.draw_background()
        self.show_status('主题颜色已保存并应用')

    def load_background(self, path, quiet=False):
        try:
            if path.strip():
                from PIL import Image, ImageOps
                with Image.open(Path(path.strip().strip('"'))) as img:
                    loaded = ImageOps.exif_transpose(img).convert('RGB').copy()
                self.background_image = loaded
            else:
                self.background_image = None
            self.db.set_setting('background_image', path.strip().strip('"'))
            self.put(self.image_path, path.strip().strip('"'))
            self.draw_background()
            if not quiet:
                self.show_status('背景已应用 · 支持 JPG / PNG / WebP 本地图片')
        except (OSError, ValueError, ImportError) as e:
            self.show_status(f'无法读取背景图片：{e}', True)

    def _resize_background(self, event):
        if event.widget is self:
            if hasattr(self, '_resize_job'):
                self.after_cancel(self._resize_job)
            self._resize_job = self.after(100, self.draw_background)

    def draw_background(self):
        self.backdrop.delete('all')
        w, h = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        if self.background_image:
            from PIL import ImageOps, ImageTk
            self._photo = ImageTk.PhotoImage(ImageOps.fit(self.background_image, (w, h)))
            self.backdrop.create_image(0, 0, image=self._photo, anchor='nw')
        else:
            for x in range(0, w, 40):
                self.backdrop.create_line(x, 0, x, h, fill='#0A2029')
            for y in range(0, h, 40):
                self.backdrop.create_line(0, y, w, y, fill='#0A2029')
        self.backdrop.create_rectangle(8, 8, w-9, h-9, outline=self.accent)

    def choose_data_path(self):
        try:
            raw = self.data_path_entry.get().strip().strip('"')
            if not raw:
                raise ValueError('请填写数据文件夹路径')
            target = Path(raw).resolve()
            target.mkdir(parents=True, exist_ok=True)
            dest = target / 'taskpool.db'
            if dest.resolve() == self.db.path.resolve():
                return self.show_status('当前已使用这个文件夹')
            if not dest.exists():
                with self.db.connect() as source:
                    with sqlite3.connect(dest) as destination:
                        source.backup(destination)
                    destination.close()
            database = Storage(dest)
            database.list_tasks()
            save_data_dir(target)
            self.db = database
            self.undo_stack.clear()
            self.undo_button.configure(state='disabled')
            self.reset_task_form()
            self.reset_reward_form()
            self.selected_reward = None
            self.refresh()
            self.show_status('数据文件夹已切换，文件未被覆盖')
        except (OSError, ValueError, sqlite3.Error) as e:
            self.show_status(f'切换失败：{e}', True)

    def destroy(self):
        for job in self.tk.call('after', 'info'):
            self.after_cancel(job)
        super().destroy()


def main():
    app = TaskPoolApp()
    app.mainloop()


if __name__ == '__main__':
    main()
