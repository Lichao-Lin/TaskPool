import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from app import Storage, TaskPoolApp, deadline_urgent

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

class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=TaskPoolApp(Storage(Path(self.temp.name)/'layout.db'))
        self.app.update()
    def tearDown(self):
        self.app.destroy()
        self.temp.cleanup()
    def test_three_columns_compact_forms_at_minimum_size(self):
        a=self.app
        a.geometry('1180x740')
        a.update()
        self.assertTrue(a.status_label.winfo_ismapped())
        self.assertLess(a.status_label.winfo_rooty()+a.status_label.winfo_height(), a.winfo_rooty()+a.winfo_height())
        self.assertEqual(len(a.forms.winfo_children()),2)
        self.assertLess(a.forms.winfo_height(),210)
        self.assertGreater(a.dashboard.winfo_height(),300)
        self.assertLess(a.reward_panel.winfo_x(),a.task_panel.winfo_x())
        self.assertLess(a.task_panel.winfo_x(),a.routine_panel.winfo_x())
        self.assertGreater(a.routine_entry.winfo_width(),60)
        for entry in [a.task_content,a.task_output,a.task_deadline,a.task_points,a.reward_name,a.reward_cost]:
            self.assertTrue(entry.winfo_ismapped())
            self.assertGreater(entry.winfo_width(),30)
    def test_inline_create_edit_delete_undo_and_errors(self):
        a=self.app
        with patch('tkinter.messagebox.showwarning',side_effect=AssertionError('modal')), patch('tkinter.messagebox.askyesno',side_effect=AssertionError('modal')):
            a.add_task()
            self.assertIn('请填写',a.status_label.cget('text'))
            a.put(a.task_content,'新任务'); a.put(a.task_output,'文档')
            a.add_task()
            rid=a.db.list_tasks()[0]['id']
            a.task_tree.selection_set(str(rid)); a.edit_task()
            a.put(a.task_content,'已修改'); a.add_task()
            self.assertEqual(a.db.list_tasks()[0]['content'],'已修改')
            a.task_tree.selection_set(str(rid)); a.delete_task()
            self.assertEqual(len(a.db.list_tasks()),0)
            a.undo()
            self.assertEqual(a.db.list_tasks()[0]['content'],'已修改')
    def test_undo_does_not_overwrite_other_window_changes(self):
        a=self.app
        a.put(a.task_content,'本窗口'); a.put(a.task_output,'输出'); a.add_task()
        a.db.add_task('另一窗口','输出','2030-01-01 12:00',10)
        a.undo()
        self.assertEqual(len(a.db.list_tasks()),2)
        self.assertIn('其他窗口',a.status_label.cget('text'))

    def test_reward_labels_rotate_outwards(self):
        a=self.app
        for i in range(6):
            a.db.add_reward('奖励'+str(i),'说明',10)
        a.refresh(); a.update()
        angles=[float(a.orbit.itemcget(item,'angle')) for item in a.orbit.find_all()
                if a.orbit.type(item)=='text' and any(t.startswith('reward') for t in a.orbit.gettags(item))]
        self.assertEqual(len(set(angles)),6)
        self.assertNotIn(0,angles)
        self.assertFalse(any(a.orbit.type(i) in ('rectangle','polygon') for i in a.orbit.find_all()))

    def test_routine_edit_and_checks_in_panel(self):
        a=self.app
        a.put(a.routine_entry,'每日阅读'); a.add_routine()
        rid=a.db.list_routines('work')[0]['id']
        a.check_routine(rid,True)
        self.assertEqual(a.db.list_routines('work')[0]['count'],1)
        a.check_routine(rid,False)
        self.assertEqual(a.db.list_routines('work')[0]['count'],0)
        a.mode.set('rest'); a.switch_mode()
        self.assertEqual(a.db.list_routines('rest'),[])
    def test_theme_and_invalid_image_are_inline(self):
        a=self.app
        a.preset('#010203','#AABBCC','#55CCFF')
        self.assertEqual(a.db.get_setting('text',''),'#AABBCC')
        a.load_background('Z:/does-not-exist.png')
        self.assertIn('无法读取',a.status_label.cget('text'))
        a.toggle_settings(); a.update()
        self.assertTrue(a.settings_panel.winfo_ismapped())
        a.toggle_settings(); a.update()
        self.assertFalse(a.settings_panel.winfo_ismapped())

if __name__=='__main__':
    unittest.main()
