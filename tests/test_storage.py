import tempfile
import unittest
from pathlib import Path

from app import Storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Storage(Path(self.temp.name) / "test.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_task_completion_credits_once(self):
        self.db.add_task("写总结", "一页文档", "2026-09-08 18:00", 20)
        task = self.db.list_tasks()[0]
        self.assertEqual(self.db.complete_task(task["id"]), 20)
        self.assertEqual(self.db.balance(), 20)
        with self.assertRaisesRegex(ValueError, "已经完成"):
            self.db.complete_task(task["id"])
        self.assertEqual(self.db.balance(), 20)

    def test_reward_requires_enough_points(self):
        self.db.add_reward("看电影", "任选一部", 50)
        reward = self.db.list_rewards()[0]
        with self.assertRaisesRegex(ValueError, "积分不足"):
            self.db.redeem_reward(reward["id"])

    def test_reward_redemption_debits_balance(self):
        self.db.add_task("完成项目", "可运行版本", "2026-09-08 18:00", 100)
        self.db.complete_task(self.db.list_tasks()[0]["id"])
        self.db.add_reward("游戏一小时", "计时放松", 30)
        cost, name = self.db.redeem_reward(self.db.list_rewards()[0]["id"])
        self.assertEqual((cost, name), (30, "游戏一小时"))
        self.assertEqual(self.db.balance(), 70)

    def test_deleting_completed_task_reverses_its_credit(self):
        self.db.add_task("整理", "清空桌面", "2026-09-08 18:00", 15)
        task_id = self.db.list_tasks()[0]["id"]
        self.db.complete_task(task_id)
        self.db.delete_task(task_id)
        self.assertEqual(self.db.balance(), 0)


if __name__ == "__main__":
    unittest.main()
