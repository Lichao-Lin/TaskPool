import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from app import Storage, Api, deadline_urgent

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Storage(Path(self.temp.name)/'test.db')
    def tearDown(self):
        self.temp.cleanup()
    def test_subtasks_credit_completion_and_undo(self):
        parent=self.db.add_task('项目','交付','2030-01-01 12:00',50)
        child=self.db.add_task('实验','表格','2030-01-01 12:00',10,parent)
        with self.assertRaisesRegex(ValueError,'子任务'):
            self.db.complete_task(parent)
        self.db.complete_task(child)
        self.db.complete_task(parent)
        snapshot=self.db.snapshot()
        self.db.delete_task(parent)
        self.assertEqual(self.db.list_tasks(),[])
        self.assertEqual(self.db.balance(),0)
        self.db.restore(snapshot)
        self.assertEqual(self.db.balance(),60)
        self.assertEqual(len(self.db.list_tasks()),2)
    def test_routine_rollover_modes_and_toggle_idempotency(self):
        rid=self.db.add_routine('work','阅读')
        self.db.add_routine('rest','散步')
        self.db.toggle_routine(rid,True,'2026-09-07')
        self.db.toggle_routine(rid,True,'2026-09-07')
        today=self.db.list_routines('work','2026-09-07')[0]
        tomorrow=self.db.list_routines('work','2026-09-08')[0]
        self.assertEqual((today['checked'],today['count']),(1,1))
        self.assertEqual((tomorrow['checked'],tomorrow['count']),(0,1))
        self.db.toggle_routine(rid,True,'2026-09-08')
        self.db.toggle_routine(rid,False,'2026-09-08')
        self.assertEqual(self.db.list_routines('work','2026-09-08')[0]['count'],1)
        self.assertEqual(self.db.list_routines('rest')[0]['content'],'散步')
        self.assertEqual(Storage(self.db.path).list_routines('work')[0]['count'],1)
    def test_deadline_boundary(self):
        now=datetime(2026,9,7,12)
        self.assertTrue(deadline_urgent('2026-09-09 12:00',now))
        self.assertFalse(deadline_urgent('2026-09-09 12:01',now))
        self.assertTrue(deadline_urgent('2026-09-06 12:00',now))
    def test_migration_from_v1_preserves_data(self):
        import sqlite3
        legacy=Path(self.temp.name)/'legacy.db'
        with sqlite3.connect(legacy) as c:
            c.execute('CREATE TABLE tasks(id INTEGER PRIMARY KEY, content TEXT, output TEXT, deadline TEXT, points INTEGER, status TEXT, created_at TEXT, completed_at TEXT)')
            c.execute("INSERT INTO tasks VALUES(1,'旧任务','旧产出','2026-10-01 12:00',10,'todo','2026-09-01',NULL)")
        c.close()
        migrated=Storage(legacy)
        self.assertEqual(migrated.list_tasks()[0]['content'],'旧任务')
        self.assertIsNone(migrated.list_tasks()[0]['parent_id'])
        migrated.add_task('子任务','输出','2026-10-01 12:00',5,1)
        self.assertEqual(len(Storage(legacy).list_tasks()),2)

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.api=Api(Storage(Path(self.temp.name)/'api.db'))
    def tearDown(self): self.temp.cleanup()
    def task(self):
        r=self.api.action('task_save',dict(content='任务',output='文档',deadline='2030-01-01T18:00',points=100))
        self.assertTrue(r['ok'])
        return r['state']['tasks'][0]['id']
    def test_completion_and_redemption_archive_once(self):
        task_id=self.task()
        r=self.api.action('task_complete',{'id':task_id})
        self.assertEqual(r['state']['tasks'][0]['status'],'done')
        self.assertEqual(r['state']['balance'],100)
        self.api.action('reward_save',dict(name='咖啡',cost=20))
        rid=self.api.state()['rewards'][0]['id']
        r=self.api.action('reward_redeem',{'id':rid})
        self.assertTrue(r['ok'])
        self.assertTrue(r['state']['rewards'][0]['archived_at'])
        self.assertEqual(len(r['state']['ledger']),2)
        self.assertFalse(self.api.action('reward_redeem',{'id':rid})['ok'])
        self.assertEqual(self.api.state()['balance'],80)
        r=self.api.action('undo')
        self.assertEqual(r['state']['balance'],100)
        self.assertIsNone(r['state']['rewards'][0]['archived_at'])
    def test_validation_is_structured(self):
        self.assertFalse(self.api.action('task_save',dict(content='',output='',deadline='',points=0))['ok'])
        self.assertFalse(self.api.setting('text','white')['ok'])
        self.assertTrue(self.api.setting('text','#aabbcc')['ok'])
        self.assertTrue(self.api.setting('panel_opacity','.2')['ok'])
        self.assertFalse(self.api.setting('unknown','value')['ok'])
    def test_undo_preserves_external_changes(self):
        self.task()
        self.api.db.add_reward('外部修改','',10)
        self.assertFalse(self.api.action('undo')['ok'])
        self.assertEqual(len(self.api.state()['rewards']),1)
    def test_settings_and_state_survive_restart(self):
        self.task();self.api.setting('panel_opacity','.3')
        other=Api(Storage(self.api.db.path))
        self.assertEqual(other.state()['settings']['panel_opacity'],'.3')
        self.assertEqual(len(other.state()['tasks']),1)

if __name__=='__main__': unittest.main()
