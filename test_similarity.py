import os
import shutil
import tempfile
from pathlib import Path
from disk_cleaner_gui import are_folders_similar, normalize_folder_name, detect_file_nature

def test_similarity_matching():
    print("[1] Testing Folder Name & Nature Similarity...")
    
    # Test normalization & similarity
    n1 = normalize_folder_name("My_Projects_2026_Backup")
    n2 = normalize_folder_name("My Projects 2026")
    print(f"  Normalized: '{n1}' vs '{n2}'")
    
    tmp = Path(tempfile.mkdtemp())
    try:
        d1 = tmp / "My_Projects_2026_Backup"
        d2 = tmp / "My Projects 2026"
        d1.mkdir()
        d2.mkdir()
        
        # Add similar image files
        (d1 / "photo1.jpg").write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01")
        (d2 / "photo2.jpg").write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01")
        
        is_sim = are_folders_similar(d1, d2, threshold=0.85)
        print(f"  Similarity Match Result: {is_sim}")
        assert is_sim, "Folders should be recognized as similar!"
        print("  ✓ Similarity matching test PASSED")
    finally:
        shutil.rmtree(tmp)

if __name__ == "__main__":
    test_similarity_matching()
    print("\nAll Similarity Tests Passed!")
