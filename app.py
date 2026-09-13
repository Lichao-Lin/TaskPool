from __future__ import annotations
import base64
import ctypes
import json
import mimetypes
import os
import re
import sqlite3
import sys
import threading
from datetime import datetime
from pathlib import Path
from storage import Storage, deadline_urgent, save_data_dir, APP_VERSION, app_config_dir

class Api:
    def __init__(self, storage=None):
        self.db = storage or Storage()
        self._lock = threading.RLock()
        self._undo = []
        self._day = datetime.now().date().isoformat()

    def state(self):
        with self._lock:
            day = datetime.now().date().isoformat()
            if day != self._day:
                self._undo.clear()
                self._day = day
            tasks = [dict(t) for t in self.db.list_tasks()]
            for t in tasks:
                t['urgent'] = t['status'] != 'done' and deadline_urgent(t['deadline'])
            rewards = [dict(r) for r in self.db.list_rewards()]
            with self.db.connect() as conn:
                ledger = [dict(r) for r in conn.execute('SELECT * FROM ledger ORDER BY id DESC')]
                settings = {r['key']: r['value'] for r in conn.execute('SELECT * FROM settings')}
            return dict(tasks=tasks, rewards=rewards, ledger=ledger, routines={m:[dict(r) for r in self.db.list_routines(m)] for m in ['work','rest']},
                        balance=self.db.balance(), settings=settings, day=day, canUndo=bool(self._undo), dataPath=str(self.db.path.parent),version=APP_VERSION)

    @staticmethod
    def _positive(value):
        n = int(value)
        if n <= 0:
            raise ValueError('积分需要大于 0')
        return n

    @staticmethod
    def _required(value, name):
        text = str(value).strip()
        if not text:
            raise ValueError('请填写'+name)
        return text

    def action(self, kind, payload=None):
        p = payload or {}
        with self._lock:
            try:
                self.state()
                before = self.db.snapshot()
                if kind == 'task_save':
                    text = self._required(p.get('content',''), '任务内容')
                    output = self._required(p.get('output',''), '产出要求')
                    deadline = datetime.strptime(p.get('deadline','').replace('T',' '), '%Y-%m-%d %H:%M').strftime('%Y-%m-%d %H:%M')
                    points = self._positive(p['points'])
                    if p.get('id'):
                        self.db.update_task(int(p['id']), text, output, deadline, points)
                    else:
                        self.db.add_task(text, output, deadline, points, p.get('parent_id'))
                elif kind == 'task_complete': self.db.complete_task(int(p['id']))
                elif kind == 'task_delete': self.db.delete_task(int(p['id']))
                elif kind == 'reward_save':
                    name = self._required(p.get('name',''), '奖励名称')
                    cost = self._positive(p['cost'])
                    if p.get('id'): self.db.update_reward(int(p['id']),name,p.get('description',''),cost)
                    else: self.db.add_reward(name,p.get('description',''),cost)
                elif kind == 'reward_redeem': self.db.redeem_reward(int(p['id']))
                elif kind == 'reward_delete': self.db.delete_reward(int(p['id']))
                elif kind == 'routine_save':
                    if p.get('id'): self.db.update_routine(int(p['id']),p['content'])
                    else: self.db.add_routine(p['mode'],p['content'])
                elif kind == 'routine_check': self.db.toggle_routine(int(p['id']),bool(p['checked']))
                elif kind == 'routine_delete': self.db.delete_routine(int(p['id']))
                elif kind == 'undo':
                    if not self._undo: raise ValueError('没有可撤销的操作')
                    snapshot, expected = self._undo[-1]
                    if before != expected:
                        self._undo.clear()
                        raise ValueError('数据在其他窗口更新，已清空旧撤销记录')
                    self.db.restore(snapshot)
                    self._undo.pop()
                    return {'ok':True,'state':self.state()}
                else: raise ValueError('不支持的操作')
                self._undo.append((before,self.db.snapshot()))
                self._undo = self._undo[-30:]
                return {'ok':True,'state':self.state()}
            except (ValueError,KeyError,TypeError,sqlite3.Error,OSError) as e:
                return {'ok':False,'error':str(e)}

    def setting(self, key, value):
        with self._lock:
            try:
                if key in ['background','text','accent']:
                    if not re.fullmatch(r'#[0-9A-Fa-f]{6}',value): raise ValueError('颜色格式：#RRGGBB')
                elif key == 'panel_opacity':
                    if not .08 <= float(value) <= .9: raise ValueError('透明度超出范围')
                elif key == 'routine_mode':
                    if value not in ['work','rest']: raise ValueError('日期类型无效')
                elif key == 'background_data':
                    if len(value)>24_000_000 or (value and not re.match(r'^data:image/(png|jpeg|webp);base64,',value)):
                        raise ValueError('请选择小于 18 MB 的 PNG/JPG/WebP 图片')
                else: raise ValueError('未知设置')
                self.db.set_setting(key,str(value))
                return {'ok':True}
            except (ValueError,sqlite3.Error) as e: return {'ok':False,'error':str(e)}

    def background(self, path):
        try:
            from PIL import Image
            import io
            if not path.strip(): return {'ok':True,'data':''}
            with Image.open(Path(path.strip().strip('"'))) as image:
                image.thumbnail((3840,2160))
                buf=io.BytesIO();image.convert('RGB').save(buf,format='JPEG',quality=92)
            data='data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()
            self.db.set_setting('background_data',data)
            return {'ok':True,'data':data}
        except Exception as e: return {'ok':False,'error':f'无法读取背景：{e}'}

    def change_data(self, directory):
        with self._lock:
            try:
                target = Path(self._required(directory,'数据文件夹')).resolve()
                target.mkdir(parents=True,exist_ok=True)
                path=target/'taskpool.db'
                if path != self.db.path.resolve() and not path.exists():
                    with self.db.connect() as source:
                        conn=sqlite3.connect(path)
                        try: source.backup(conn)
                        finally: conn.close()
                candidate=Storage(path);candidate.list_tasks()
                save_data_dir(target);self.db=candidate;self._undo.clear()
                return {'ok':True,'state':self.state()}
            except Exception as e: return {'ok':False,'error':str(e)}


def main():
    if sys.platform=='win32':
        try: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception: pass
    import webview
    root = Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    api = Api(Storage(os.environ['TERMXK_TEST_DB']) if os.getenv('TERMXK_TEST_DB') else None)
    window=webview.create_window('Termxk', html=(root/'frontend.html').read_text(encoding='utf-8'), js_api=api,
        width=1480,height=900,min_size=(1080,700),background_color='#000000',confirm_close=False,text_select=True)
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG']=False
    webview.settings['ALLOW_FILE_URLS']=False
    webview.start(gui='edgechromium',icon=str(root/'assets'/'termxk.ico'),storage_path=str(app_config_dir()/'webview'))

if __name__=='__main__': main()
