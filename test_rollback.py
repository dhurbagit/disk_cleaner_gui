import os
import shutil
import tempfile
from pathlib import Path
from disk_cleaner_gui import SafetyVault, ModernDiskCleanerApp

def test_rollback_system():
    print("[1] Testing SafetyVault & Rollback Mechanism...")
    
    tmp = Path(tempfile.mkdtemp())
    try:
        # Create test directory layout
        (tmp / "test_file.txt").write_text("Hello World")
        d1 = tmp / "SubFolder"
        d1.mkdir()
        (d1 / "image.jpg").write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01")
        
        # Test SafetyVault deletion recording
        vault = SafetyVault(tmp)
        vault.record_deletion(d1 / "image.jpg", is_folder=False)
        vault.record_deletion(d1, is_folder=True)
        vault.save_transaction()
        
        assert not (d1 / "image.jpg").exists(), "Image should be moved to trash!"
        assert not d1.exists(), "SubFolder should be moved to trash!"
        
        # Test Rollback
        app = ModernDiskCleanerApp.__new__(ModernDiskCleanerApp)
        app.log_area = type("MockLog", (), {"config": lambda *a, **k: None, "insert": lambda *a, **k: None, "see": lambda *a, **k: None})()
        app._log = lambda text, tag=None: print(f"    LOG: {text}")
        app._on_finish = lambda: None
        
        app._rollback_last_operation(tmp)
        
        assert d1.exists(), "SubFolder should be restored!"
        assert (d1 / "image.jpg").exists(), "Image file should be restored!"
        print("  ✓ SafetyVault & Rollback verification PASSED!")
    finally:
        shutil.rmtree(tmp)

if __name__ == "__main__":
    test_rollback_system()
    print("\nAll Rollback Tests Passed Successfully!")
