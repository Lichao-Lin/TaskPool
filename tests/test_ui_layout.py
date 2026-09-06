import tempfile
import unittest
from pathlib import Path

from app import Storage, TaskPoolApp


class LayoutTests(unittest.TestCase):
    def test_dashboard_is_above_two_input_panels(self):
        with tempfile.TemporaryDirectory() as temp:
            app = TaskPoolApp(Storage(Path(temp) / "layout.db"))
            try:
                app.update()
                body_children = app.winfo_children()[1].winfo_children()
                dashboard, forms = body_children[0], body_children[1]
                self.assertLess(dashboard.winfo_y(), forms.winfo_y())
                self.assertEqual(len(forms.winfo_children()), 2)
                left, right = forms.winfo_children()
                self.assertAlmostEqual(left.winfo_width(), right.winfo_width(), delta=12)
                self.assertGreater(dashboard.winfo_height(), 250)
                self.assertGreater(app.task_panel.winfo_width(), app.reward_panel.winfo_width() * 1.8)
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
