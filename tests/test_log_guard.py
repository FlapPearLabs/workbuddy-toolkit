import os
import sys
import time
import shutil
import tempfile
import unittest
import importlib.util

import importlib.machinery

def load_log_guard():
    loader = importlib.machinery.SourceFileLoader("workbuddy_log_guard", os.path.join(os.path.dirname(__file__), "..", "bin", "workbuddy-log-guard"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module

class TestLogGuard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        os.environ["WB_LOG_DIR"] = self.temp_dir
        os.environ["WB_TRACES_DIR"] = os.path.join(self.temp_dir, "traces")
        self.guard = load_log_guard()
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if "WB_LOG_DIR" in os.environ:
            del os.environ["WB_LOG_DIR"]
        if "WB_TRACES_DIR" in os.environ:
            del os.environ["WB_TRACES_DIR"]

    def test_is_file_open_windows(self):
        original_name = os.name
        os.name = 'nt'
        
        filepath = os.path.join(self.temp_dir, "test.log")
        with open(filepath, "w") as f:
            f.write("test")
            
        original_rename = os.rename
        def mock_rename(src, dst):
            e = OSError("Sharing violation")
            e.winerror = 32
            raise e
            
        os.rename = mock_rename
        
        try:
            self.assertTrue(self.guard.is_file_open(filepath, set()))
        finally:
            os.rename = original_rename
            os.name = original_name

    def test_cleanup_locked_sandbox_file(self):
        sandbox_dir = os.path.join(self.temp_dir, "sandbox", "old_date")
        os.makedirs(sandbox_dir)
        filepath = os.path.join(sandbox_dir, "locked.log")
        with open(filepath, "w") as f:
            f.write("A" * 1024)
            
        old_time = time.time() - (3600 * 48)
        os.utime(filepath, (old_time, old_time))
        
        original_is_file_open = self.guard.is_file_open
        self.guard.is_file_open = lambda fp, ofs: True
        
        try:
            self.guard.main()
            self.assertTrue(os.path.exists(filepath))
            self.assertEqual(os.path.getsize(filepath), 0)
        finally:
            self.guard.is_file_open = original_is_file_open

if __name__ == '__main__':
    unittest.main()
