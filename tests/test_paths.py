import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from diary.paths import application_dir


class PathTests(unittest.TestCase):
    def test_source_data_follows_project_not_working_directory(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(application_dir(), Path(__file__).resolve().parent.parent)

    def test_frozen_data_follows_executable_not_extraction_directory(self):
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", str(Path("portable") / "ShiguangDiary.exe")), \
             patch.object(sys, "_MEIPASS", str(Path("temporary-extraction")), create=True):
            self.assertEqual(application_dir(), Path("portable").resolve())


if __name__ == "__main__":
    unittest.main()
