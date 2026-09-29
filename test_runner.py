import os
import shutil
import tempfile
from pathlib import Path

from disk_cleaner_gui import (
    get_file_hash,
    detect_file_nature,
    ModernDiskCleanerApp
)

def test_all():
    print("[1] Testing Nature Detection...")
    tmp = Path(tempfile.mkdtemp())
    try:
        img_file = tmp / "test_img.jpg"
        img_file.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01")
        assert detect_file_nature(img_file) == "Images", f"Expected Images, got {detect_file_nature(img_file)}"

        pdf_file = tmp / "document.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 header contents...")
        assert detect_file_nature(pdf_file) == "Documents", f"Expected Documents, got {detect_file_nature(pdf_file)}"

        py_file = tmp / "script.py"
        py_file.write_text("print('hello world')")
        assert detect_file_nature(py_file) == "Code_and_Scripts", f"Expected Code_and_Scripts, got {detect_file_nature(py_file)}"

        zip_file = tmp / "archive.zip"
        zip_file.write_bytes(b"PK\x03\x04\x0a\x00\x00\x00")
        assert detect_file_nature(zip_file) == "Archives", f"Expected Archives, got {detect_file_nature(zip_file)}"

        print("  ✓ Nature detection tests PASSED")
    finally:
        shutil.rmtree(tmp)

    print("[2] Testing File & Folder Deduplication...")
    test_root = Path(tempfile.mkdtemp())
    try:
        dir_a = test_root / "Folder_A"
        dir_b = test_root / "Folder_B"
        dir_a.mkdir()
        dir_b.mkdir()

        f1_a = dir_a / "sample.txt"
        f1_b = dir_b / "sample.txt"
        content = "Identical content for duplicate folder test"
        f1_a.write_text(content)
        f1_b.write_text(content)

        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        app = ModernDiskCleanerApp(root)

        app._find_and_remove_duplicate_folders(test_root, dry_run=False)
        remaining_dirs = [d.name for d in test_root.iterdir() if d.is_dir()]
        assert len(remaining_dirs) == 1, f"Expected 1 folder remaining, found: {remaining_dirs}"
        print("  ✓ Duplicate folder removal test PASSED")

        app._organize_directory(test_root, dry_run=False)
        docs_dir = test_root / "Documents"
        assert docs_dir.exists(), "Documents folder should be created"
        print("  ✓ File organization test PASSED")

        root.destroy()
    finally:
        shutil.rmtree(test_root)

    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_all()
