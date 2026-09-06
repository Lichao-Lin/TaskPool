from __future__ import annotations

import math
import json
import os
import random
import shutil
import sqlite3
import sys
import tkinter as tk
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk


APP_NAME = "TaskPool"
APP_VERSION = "1.0.0"
DEFAULT_ACCENT = "#7CFFB2"
BG = "#000000"
PANEL = "#0B1016"
PANEL_2 = "#121A23"
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

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def add_task(self, content: str, output: str, deadline: str, points: int):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO tasks(content, output, deadline, points, created_at) VALUES(?,?,?,?,?)",
                (content.strip(), output.strip(), deadline, points, self._now()),
            )

    def list_tasks(self):
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM tasks ORDER BY status ASC, deadline ASC, id DESC"
            ).fetchall()

    def complete_task(self, task_id: int) -> int:
        with self.connect() as conn:
            task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task:
                raise ValueError("任务不存在")
            if task["status"] == "done":
                raise ValueError("该任务已经完成")
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


class TaskPoolApp(tk.Tk):
    def __init__(self, storage: Storage | None = None):
        super().__init__()
        self.db = storage or Storage()
        self.accent = self.db.get_setting("accent", DEFAULT_ACCENT)
        self.title(f"TaskPool 任务积分池  ·  v{APP_VERSION}")
        self.geometry("1180x820")
        self.minsize(980, 720)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build_style()
        self._build_ui()
        self.refresh()

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL_2,
                        bordercolor=PANEL_2, lightcolor=PANEL_2, darkcolor=PANEL_2,
                        font=("Microsoft YaHei UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=self.accent,
                        font=("Consolas", 20, "bold"))
        style.configure("Score.TLabel", background=PANEL, foreground=self.accent,
                        font=("Consolas", 26, "bold"))
        style.configure("TEntry", padding=8, insertcolor=TEXT)
        style.configure("TButton", padding=(12, 8), background=PANEL_2, foreground=TEXT,
                        borderwidth=0, focusthickness=0)
        style.map("TButton", background=[("active", self.accent)], foreground=[("active", BG)])
        style.configure("Accent.TButton", background=self.accent, foreground=BG,
                        font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#FFFFFF")])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=35, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL_2, foreground=self.accent,
                        padding=8, font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", self.accent)],
                  foreground=[("selected", BG)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(18, 9))
        style.map("TNotebook.Tab", background=[("selected", PANEL_2)],
                  foreground=[("selected", self.accent)])

    def _build_ui(self):
        header = ttk.Frame(self, padding=(24, 18, 24, 10))
        header.pack(fill="x")
        ttk.Label(header, text="> TASK_POOL", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="本地任务 · 积分驱动 · 奖励兑现", foreground=MUTED).pack(side="left", padx=18)
        ttk.Button(header, text="🎨 主题色", command=self.choose_color).pack(side="right")
        ttk.Button(header, text="📁 数据文件夹", command=self.choose_data_path).pack(side="right", padx=8)

        body = ttk.Frame(self, padding=(24, 8, 24, 20))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=3)
        body.rowconfigure(1, weight=0)
        dashboard = ttk.Frame(body)
        dashboard.grid(row=0, column=0, sticky="nsew", pady=(0, 14))
        self._build_dashboard(dashboard)

        forms = ttk.Frame(body)
        forms.grid(row=1, column=0, sticky="ew")
        forms.columnconfigure(0, weight=1, uniform="input_panels")
        forms.columnconfigure(1, weight=1, uniform="input_panels")
        task_form = ttk.Frame(forms)
        reward_form = ttk.Frame(forms)
        task_form.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        reward_form.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self._build_task_form(task_form)
        self._build_reward_form(reward_form)

        self.fx = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.toast = tk.Label(self, bg=self.accent, fg=BG, font=("Microsoft YaHei UI", 12, "bold"), padx=22, pady=12)

    def _panel(self, parent, title: str, subtitle: str):
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=18)
        ttk.Label(frame, text=title, style="Panel.TLabel",
                  font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frame, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(2, 14))
        return frame

    def _field(self, parent, label: str):
        ttk.Label(parent, text=label, style="Muted.TLabel").pack(anchor="w", pady=(5, 4))
        entry = ttk.Entry(parent)
        entry.pack(fill="x", pady=(0, 6))
        return entry

    def _build_task_form(self, parent):
        panel = self._panel(parent, "01 / 新建任务", "填写任务、产出、截止时间与可得积分")
        panel.pack(fill="both", expand=True)
        self.task_content = self._field(panel, "任务内容 *")
        self.task_output = self._field(panel, "产出要求 *")
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill="x", pady=(5, 0))
        left = ttk.Frame(row, style="Panel.TFrame")
        right = ttk.Frame(row, style="Panel.TFrame")
        left.pack(side="left", fill="x", expand=True, padx=(0, 6))
        right.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.task_deadline = self._field(left, "截止时间 *")
        self.task_deadline.insert(0, datetime.now().strftime("%Y-%m-%d 23:59"))
        self.task_points = self._field(right, "任务积分 *")
        self.task_points.insert(0, "10")
        ttk.Button(panel, text="+ 添加到任务列表", style="Accent.TButton",
                   command=self.add_task).pack(fill="x", pady=(10, 0))
        self.task_content.bind("<Return>", lambda _: self.task_output.focus_set())

    def _build_reward_form(self, parent):
        panel = self._panel(parent, "02 / 自定义奖池", "把想要的休息、体验或礼物放进奖池")
        panel.pack(fill="both", expand=True)
        self.reward_name = self._field(panel, "奖励名称 *")
        self.reward_description = self._field(panel, "奖励说明")
        self.reward_cost = self._field(panel, "所需积分 *")
        self.reward_cost.insert(0, "50")
        ttk.Button(panel, text="+ 放入奖励池", style="Accent.TButton",
                   command=self.add_reward).pack(fill="x", pady=(10, 0))

    def _build_dashboard(self, parent):
        stat = ttk.Frame(parent, style="Panel.TFrame", padding=(18, 12))
        stat.pack(fill="x", pady=(0, 12))
        self.balance_label = ttk.Label(stat, text="0 PTS", style="Score.TLabel")
        self.balance_label.pack(side="left")
        self.stats_label = ttk.Label(stat, text="", style="Muted.TLabel")
        self.stats_label.pack(side="left", padx=22)
        ttk.Label(stat, text="积分余额", style="Muted.TLabel").pack(side="right")

        workspace = ttk.Frame(parent)
        workspace.pack(fill="both", expand=True)
        workspace.columnconfigure(0, weight=1, uniform="workspace")
        workspace.columnconfigure(1, weight=2, uniform="workspace")
        workspace.rowconfigure(0, weight=1)

        reward_tab = ttk.Frame(workspace, style="Panel.TFrame", padding=12)
        task_tab = ttk.Frame(workspace, style="Panel.TFrame", padding=12)
        reward_tab.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        task_tab.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self.reward_panel = reward_tab
        self.task_panel = task_tab

        ttk.Label(reward_tab, text="★ REWARD POOL / 奖池", style="Panel.TLabel",
                  font=("Consolas", 11, "bold")).pack(anchor="w", pady=(0, 9))
        ttk.Label(task_tab, text="> ACTIVE TASKS / 当前任务", style="Panel.TLabel",
                  font=("Consolas", 11, "bold")).pack(anchor="w", pady=(0, 9))

        task_cols = ("content", "output", "deadline", "points", "status")
        self.task_tree = ttk.Treeview(task_tab, columns=task_cols, show="headings", selectmode="browse")
        for col, title, width in zip(task_cols, ("任务内容", "产出要求", "截止时间", "积分", "状态"), (170, 170, 130, 60, 70)):
            self.task_tree.heading(col, text=title)
            self.task_tree.column(col, width=width, minwidth=55, anchor="center" if col in ("points", "status") else "w")
        self.task_tree.pack(fill="both", expand=True)
        self.task_tree.tag_configure("done", foreground=MUTED)
        bar = ttk.Frame(task_tab, style="Panel.TFrame")
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="✓ 达成任务", style="Accent.TButton", command=self.complete_selected).pack(side="left")
        ttk.Button(bar, text="删除", command=self.delete_task).pack(side="left", padx=8)
        ttk.Label(bar, text="双击任务也可完成", style="Muted.TLabel").pack(side="right")
        self.task_tree.bind("<Double-1>", lambda _: self.complete_selected())

        reward_cols = ("name", "cost", "state")
        self.reward_tree = ttk.Treeview(reward_tab, columns=reward_cols, show="headings", selectmode="browse")
        for col, title, width in zip(reward_cols, ("奖励", "积分", "状态"), (150, 60, 70)):
            self.reward_tree.heading(col, text=title)
            self.reward_tree.column(col, width=width, minwidth=50, anchor="center" if col in ("cost", "state") else "w")
        self.reward_tree.pack(fill="both", expand=True)
        bar2 = ttk.Frame(reward_tab, style="Panel.TFrame")
        bar2.pack(fill="x", pady=(10, 0))
        ttk.Button(bar2, text="★ 兑换奖励", style="Accent.TButton", command=self.redeem_selected).pack(side="left")
        ttk.Button(bar2, text="删除", command=self.delete_reward).pack(side="left", padx=8)
        self.reward_tree.bind("<Double-1>", lambda _: self.redeem_selected())

    @staticmethod
    def _required(entry: ttk.Entry, name: str) -> str:
        value = entry.get().strip()
        if not value:
            entry.focus_set()
            raise ValueError(f"请填写{name}")
        return value

    @staticmethod
    def _positive_int(value: str, name: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(f"{name}需要填写正整数") from exc
        if parsed <= 0:
            raise ValueError(f"{name}需要大于 0")
        return parsed

    def add_task(self):
        try:
            content = self._required(self.task_content, "任务内容")
            output = self._required(self.task_output, "产出要求")
            deadline = self._required(self.task_deadline, "截止时间")
            datetime.strptime(deadline, "%Y-%m-%d %H:%M")
            points = self._positive_int(self.task_points.get().strip(), "任务积分")
            self.db.add_task(content, output, deadline, points)
        except ValueError as exc:
            messagebox.showwarning("还差一点", str(exc), parent=self)
            return
        self.task_content.delete(0, "end")
        self.task_output.delete(0, "end")
        self.task_content.focus_set()
        self.refresh()
        self.show_toast("任务已加入队列  +1")

    def add_reward(self):
        try:
            name = self._required(self.reward_name, "奖励名称")
            cost = self._positive_int(self.reward_cost.get().strip(), "所需积分")
            self.db.add_reward(name, self.reward_description.get(), cost)
        except ValueError as exc:
            messagebox.showwarning("还差一点", str(exc), parent=self)
            return
        self.reward_name.delete(0, "end")
        self.reward_description.delete(0, "end")
        self.reward_name.focus_set()
        self.refresh()
        self.show_toast("奖励已放入奖池  ★")

    def _selected_id(self, tree: ttk.Treeview, thing: str):
        selected = tree.selection()
        if not selected:
            messagebox.showinfo("请选择", f"请先选择一个{thing}", parent=self)
            return None
        return int(selected[0])

    def complete_selected(self):
        task_id = self._selected_id(self.task_tree, "任务")
        if task_id is None:
            return
        try:
            points = self.db.complete_task(task_id)
        except ValueError as exc:
            messagebox.showinfo("提示", str(exc), parent=self)
            return
        self.refresh()
        self.celebrate(f"任务达成  +{points} PTS", gain=True)

    def redeem_selected(self):
        reward_id = self._selected_id(self.reward_tree, "奖励")
        if reward_id is None:
            return
        try:
            cost, name = self.db.redeem_reward(reward_id)
        except ValueError as exc:
            self.shake()
            messagebox.showwarning("无法兑换", str(exc), parent=self)
            return
        self.refresh()
        self.celebrate(f"已解锁「{name}」  -{cost} PTS", gain=False)

    def delete_task(self):
        task_id = self._selected_id(self.task_tree, "任务")
        if task_id is not None and messagebox.askyesno("删除任务", "删除后，与该任务关联的积分也会撤销。确定继续？", parent=self):
            self.db.delete_task(task_id)
            self.refresh()

    def delete_reward(self):
        reward_id = self._selected_id(self.reward_tree, "奖励")
        if reward_id is not None and messagebox.askyesno("删除奖励", "确定从奖池删除这个奖励？历史兑换流水会保留。", parent=self):
            self.db.delete_reward(reward_id)
            self.refresh()

    def refresh(self):
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)
        for task in self.db.list_tasks():
            status = "已完成" if task["status"] == "done" else "进行中"
            self.task_tree.insert("", "end", iid=str(task["id"]),
                                  values=(task["content"], task["output"], task["deadline"], f"+{task['points']}", status),
                                  tags=("done",) if task["status"] == "done" else ())
        balance = self.db.balance()
        for item in self.reward_tree.get_children():
            self.reward_tree.delete(item)
        for reward in self.db.list_rewards():
            state = "READY" if balance >= reward["cost"] else f"差 {reward['cost'] - balance}"
            self.reward_tree.insert("", "end", iid=str(reward["id"]),
                                    values=(reward["name"], reward["cost"], state))
        total, done, spent = self.db.stats()
        self.balance_label.configure(text=f"{balance} PTS")
        self.stats_label.configure(text=f"任务 {done}/{total} 达成   ·   已兑换 {spent} 分")

    def choose_color(self):
        chosen = colorchooser.askcolor(color=self.accent, title="选择强调色", parent=self)[1]
        if chosen:
            self.accent = chosen.upper()
            self.db.set_setting("accent", self.accent)
            self._build_style()
            self.toast.configure(bg=self.accent)
            self.show_toast("主题色已立即应用")

    def choose_data_path(self):
        current = self.db.path.parent.resolve()
        selected = filedialog.askdirectory(
            title="选择 TaskPool 数据文件夹",
            initialdir=str(current),
            mustexist=False,
            parent=self,
        )
        if not selected:
            return
        target_dir = Path(selected).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        target_db = target_dir / "taskpool.db"
        if target_db.resolve() == self.db.path.resolve():
            return
        try:
            if target_db.exists():
                use_existing = messagebox.askyesno(
                    "发现已有数据",
                    "所选文件夹内已有 taskpool.db。\n\n选择“是”切换到已有数据；选择“否”取消操作（不会覆盖任何文件）。",
                    parent=self,
                )
                if not use_existing:
                    return
            elif self.db.path.exists():
                shutil.copy2(str(self.db.path), str(target_db))
            save_data_dir(target_dir)
            self.db = Storage(target_db)
            self.refresh()
        except OSError as exc:
            messagebox.showerror("无法切换数据文件夹", str(exc), parent=self)
            return
        self.show_toast("数据文件夹已切换")
        if messagebox.askyesno("切换成功", "数据已保存到新文件夹。现在打开查看？", parent=self):
            if sys.platform.startswith("win"):
                os.startfile(str(target_dir))  # type: ignore[attr-defined]
            else:
                messagebox.showinfo("数据位置", str(target_dir), parent=self)

    def show_toast(self, text: str):
        self.toast.configure(text=text, bg=self.accent)
        self.toast.place(relx=.5, y=-60, anchor="n")
        def slide(step=0):
            if step <= 12:
                y = -60 + (76 * (1 - (1 - step / 12) ** 3))
                self.toast.place_configure(y=int(y))
                self.after(18, lambda: slide(step + 1))
            else:
                self.after(1100, lambda: self.toast.place_forget())
        slide()

    def celebrate(self, text: str, gain: bool):
        self.show_toast(text)
        self.fx.place(x=0, y=0, relwidth=1, relheight=1)
        self.fx.lift()
        self.toast.lift()
        w, h = max(self.winfo_width(), 800), max(self.winfo_height(), 600)
        particles = []
        palette = [self.accent, WARNING, "#72A7FF", "#FF7AB6", "#FFFFFF"]
        origin_x, origin_y = w * .68, h * .42
        for _ in range(55):
            angle = random.uniform(math.pi * 1.08, math.pi * 1.92)
            speed = random.uniform(4, 12)
            size = random.randint(3, 8)
            item = self.fx.create_rectangle(origin_x, origin_y, origin_x + size, origin_y + size,
                                            fill=random.choice(palette), outline="")
            particles.append([item, math.cos(angle) * speed, math.sin(angle) * speed, 0.0])
        symbol = "+" if gain else "★"
        hero = self.fx.create_text(origin_x, origin_y, text=symbol, fill=self.accent,
                                   font=("Consolas", 44, "bold"))
        def tick(frame=0):
            self.fx.delete(hero) if frame == 24 else None
            for p in particles:
                p[3] += .34
                self.fx.move(p[0], p[1], p[2] + p[3])
            if frame < 50:
                self.after(20, lambda: tick(frame + 1))
            else:
                self.fx.delete("all")
                self.fx.place_forget()
        tick()

    def shake(self):
        x, y = self.winfo_x(), self.winfo_y()
        offsets = [0, -8, 8, -6, 6, -3, 3, 0]
        def move(i=0):
            if i < len(offsets):
                self.geometry(f"+{x + offsets[i]}+{y}")
                self.after(28, lambda: move(i + 1))
        move()


def main():
    app = TaskPoolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
