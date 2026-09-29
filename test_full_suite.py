import os
import shutil
import tempfile
from pathlib import Path
from disk_cleaner_gui import ModernDiskCleanerApp, SafetyVault, detect_file_nature

def test_full_suite():
    print("[1] Creating temporary test directory structure...")
    tmp = Path(tempfile.mkdtemp())
    try:
        # Create test files of various natures
        (tmp / "test_doc.pdf").write_bytes(b"%PDF-1.5 test document")
        (tmp / "photo1.jpg").write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01")
        (tmp / "photo2.jpg").write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01") # Duplicate of photo1
        (tmp / "script.py").write_text("print('hello world')")

        # Create duplicate folders
        f1 = tmp / "ProjectDocs"
        f1.mkdir()
        (f1 / "doc1.txt").write_text("Confidential Info")
        
        f2 = tmp / "ProjectDocs_Copy" # Duplicate of f1
        f2.mkdir()
        (f2 / "doc1.txt").write_text("Confidential Info")

        # Create similar folders (~85% match)
        s1 = tmp / "MyVacationPhotos"
        s1.mkdir()
        (s1 / "vac1.jpg").write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01")

        s2 = tmp / "MyVacationPhotos_backup"
        s2.mkdir()
        (s2 / "vac2.jpg").write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01")

        print("  ✓ Directory setup complete.")

        # Test Dry Run
        app = ModernDiskCleanerApp.__new__(ModernDiskCleanerApp)
        app.log_area = type("MockLog", (), {"config": lambda *a, **k: None, "insert": lambda *a, **k: None, "see": lambda *a, **k: None})()
        app._log = lambda text, tag=None: print(f"    LOG: {text}")
        app._update_stats = lambda *a, **k: None
        app._on_finish = lambda: None

        app.remove_dup_files = type("Var", (), {"get": lambda: True})()
        app.remove_dup_folders = type("Var", (), {"get": lambda: True})()
        app.merge_similar_folders = type("Var", (), {"get": lambda: True})()
        app.organize_files = type("Var", (), {"get": lambda: True})()
        app.use_safety_trash = type("Var", (), {"get": lambda: True})()
        app.is_dry_run = type("Var", (), {"get": lambda: False})() # Live Run!

        print("\n[2] Running Live Operation pipeline...")
        app._run_cleaning(tmp)

        # Assertions
        assert (tmp / "Images" / "photo1.jpg").exists(), "Photo1 should be categorized into Images!"
        assert not (tmp / "photo2.jpg").exists(), "Duplicate photo2 should be removed!"
        assert (tmp / "Documents" / "test_doc.pdf").exists(), "PDF should be categorized into Documents!"
        assert (tmp / "Code_and_Scripts" / "script.py").exists(), "Python script should be categorized into Code_and_Scripts!"
        assert not f2.exists(), "Duplicate folder f2 should be removed!"
        assert not s2.exists(), "Similar folder s2 should be merged!"

        print("\n[3] Testing Rollback on live output...")
        app._rollback_last_operation(tmp)

        assert (tmp / "photo2.jpg").exists() or (tmp / "Images" / "photo2.jpg").exists(), "Duplicate photo2 restored!"
        print("  ✓ Full Suite Verification Passed Successfully!")
    finally:
        shutil.rmtree(tmp)

if __name__ == "__main__":
    test_full_suite()
