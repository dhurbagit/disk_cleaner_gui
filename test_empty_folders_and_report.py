import os
import shutil
import tempfile
from pathlib import Path
from disk_cleaner_gui import ModernDiskCleanerApp

def test_empty_folders_and_report():
    print("[1] Setting up temporary test folder...")
    tmp = Path(tempfile.mkdtemp())
    try:
        # Create files
        (tmp / "sample.pdf").write_bytes(b"%PDF-1.4 sample content")
        
        # Create an empty directory
        empty_d = tmp / "SubFolder_Empty"
        empty_d.mkdir()

        # Create nested empty directory
        nested_empty = tmp / "NestedParent" / "SubEmpty"
        nested_empty.mkdir(parents=True)

        print("  ✓ Setup complete.")

        app = ModernDiskCleanerApp.__new__(ModernDiskCleanerApp)
        app.log_area = type("MockLog", (), {"config": lambda *a, **k: None, "insert": lambda *a, **k: None, "see": lambda *a, **k: None})()
        app._log = lambda text, tag=None: print(f"    LOG: {text}")
        app._update_stats = lambda *a, **k: None
        app._on_finish = lambda: None

        app.remove_dup_files = type("Var", (), {"get": lambda: False})()
        app.remove_dup_folders = type("Var", (), {"get": lambda: False})()
        app.merge_similar_folders = type("Var", (), {"get": lambda: False})()
        app.organize_files = type("Var", (), {"get": lambda: True})()
        app.remove_empty_folders = type("Var", (), {"get": lambda: True})()
        app.use_safety_trash = type("Var", (), {"get": lambda: True})()
        app.is_dry_run = type("Var", (), {"get": lambda: False})() # Live Run!

        print("\n[2] Executing Live Run cleaning...")
        app._run_cleaning(tmp)

        # Assertions
        assert not empty_d.exists(), "Empty folder should be removed!"
        assert not nested_empty.exists(), "Nested empty folder should be removed!"
        assert not (tmp / "NestedParent").exists(), "Parent folder should also be removed after nested empty folder is deleted!"
        
        # Check if report file was generated
        reports = list(tmp.glob("disk_cleaner_report_*.txt"))
        assert len(reports) > 0, "Detailed report file should be generated in target location!"
        
        report_text = reports[0].read_text(encoding="utf-8")
        assert "DISK CLEANER & SMART ORGANIZER REPORT" in report_text
        assert "Empty Folders Cleaned Up" in report_text
        assert "STEP-BY-STEP USER MANAGEMENT GUIDE" in report_text

        print(f"  ✓ Detailed Report File Verified at: {reports[0].name}")
        print("\n[3] Testing Rollback...")
        app._rollback_last_operation(tmp)

        assert empty_d.exists(), "Empty folder should be restored by Rollback!"
        print("  ✓ Rollback restored empty folder successfully!")
        print("  ✓ ALL TESTS PASSED SUCCESSFULLY!")

    finally:
        shutil.rmtree(tmp)

if __name__ == "__main__":
    test_empty_folders_and_report()
