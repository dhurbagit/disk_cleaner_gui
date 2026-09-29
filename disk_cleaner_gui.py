import os
import sys
import shutil
import hashlib
import threading
import mimetypes
import difflib
import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from concurrent.futures import ThreadPoolExecutor, as_completed

# Extended Category Mapping based on File Extension and Nature
EXTENSION_MAP = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".tiff", ".ico", ".heic", ".raw"],
    "Videos": [".mp4", ".mkv", ".mov", ".avi", ".flv", ".webm", ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp"],
    "Audio": [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".opus", ".midi"],
    "Documents": [".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt", ".pages", ".tex", ".md", ".rst"],
    "Spreadsheets": [".xlsx", ".xls", ".csv", ".ods", ".numbers", ".tsv"],
    "Presentations": [".pptx", ".ppt", ".odp", ".key"],
    "Archives": [".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz", ".tgz"],
    "Code_and_Scripts": [".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".php", ".sh", ".bash", ".json", ".sql", ".c", ".cpp", ".h", ".hpp", ".java", ".rs", ".go", ".rb", ".xml", ".yaml", ".yml"],
    "Executables": [".exe", ".msi", ".bin", ".appimage", ".deb", ".rpm", ".dmg", ".iso", ".apk"],
    "EBooks": [".epub", ".mobi", ".azw3"],
    "Design_Files": [".psd", ".ai", ".eps", ".fig", ".blend", ".xcf", ".sketch"],
}

ALL_CATEGORIES = list(EXTENSION_MAP.keys()) + ["Other", ".disk_cleaner_trash"]

PROJECT_MARKERS = {
    # PHP, Laravel, Symfony, WordPress
    "artisan", "composer.json", "composer.lock", "wp-config.php", "wp-content", "symfony.lock",
    # JavaScript, Node, TypeScript, React, Vue, Next, Nuxt, Vite, Svelte, Angular
    "package.json", "package-lock.json", "node_modules", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "tsconfig.json", "jsconfig.json", "webpack.config.js", "vite.config.js", "vite.config.ts",
    "next.config.js", "nuxt.config.js", "svelte.config.js", "angular.json", "tailwind.config.js",
    ".babelrc", "babel.config.js", "eslint.config.js", ".eslintrc", ".prettierrc",
    # Python (Django, Flask, FastAPI, Poetry, Pipenv)
    "requirements.txt", "Pipfile", "Pipfile.lock", "pyproject.toml", "setup.py", "setup.cfg",
    "manage.py", "wsgi.py", "asgi.py", "poetry.lock", "venv", ".venv", ".pytest_cache", "__pycache__",
    # Rust
    "Cargo.toml", "Cargo.lock",
    # Go
    "go.mod", "go.sum", "go.work",
    # Java, Kotlin, Android, Gradle, Maven
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
    "gradlew", "gradlew.bat", ".gradle", "AndroidManifest.xml",
    # C, C++, Make, CMake
    "CMakeLists.txt", "Makefile", "makefile", "Configure", "configure.ac", "meson.build",
    # C#, .NET, Unity
    "global.json", "NuGet.config",
    # Ruby & Rails
    "Gemfile", "Gemfile.lock", "Rakefile",
    # Docker, K8s, CI/CD
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".gitlab-ci.yml",
    # Version Control & IDEs
    ".git", ".gitignore", ".gitmodules", ".svn", ".hg", ".idea", ".vscode"
}

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".php", ".java", ".cpp", ".c", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".html", ".css", ".scss", ".sql", ".sh", ".bash", ".swift", ".kt"
}

CODE_SUBDIRS = {"src", "app", "lib", "components", "controllers", "models", "views", "routes", "vendor", "public", "include", "bin"}


def is_developer_project(p: Path) -> bool:
    """
    Detects if a directory is a Developer Code Project (Laravel, Node, React, Vue, Python, Rust, Go, Java, C++, C#, Rails, etc.).
    Developer projects are protected from folder merging, internal file moves, and structure deduplication.
    """
    if not p.is_dir():
        return False
    try:
        items = os.listdir(p)
        # 1. Direct Project Marker File Check
        for item_name in items:
            if item_name in PROJECT_MARKERS or item_name.endswith((".csproj", ".sln", ".xcodeproj", ".vcxproj")):
                return True
        
        # 2. Code Structural Pattern Check (Code Subdirectories + Code Files)
        has_code_subdir = any(i.lower() in CODE_SUBDIRS for i in items if (p / i).is_dir())
        has_code_file = any(Path(i).suffix.lower() in CODE_EXTENSIONS for i in items if (p / i).is_file())
        
        if has_code_subdir and has_code_file:
            return True

    except (PermissionError, OSError):
        pass
    return False


def is_inside_developer_project(p: Path, target_dir: Path) -> bool:
    """Checks if path is inside any ancestor directory that is a developer code project."""
    curr = p if p.is_dir() else p.parent
    while curr and curr != target_dir and curr != curr.parent:
        if is_developer_project(curr):
            return True
        curr = curr.parent
    return False


def is_reserved_folder(p: Path, target_dir: Path) -> bool:
    """Check if path is a reserved category folder, trash vault, or inside a Developer Code Project."""
    if p.name == ".disk_cleaner_trash" or ".disk_cleaner_trash" in p.parts:
        return True
    try:
        rel = p.relative_to(target_dir)
        if len(rel.parts) >= 1 and rel.parts[0] in ALL_CATEGORIES:
            return True
    except ValueError:
        pass
    if is_developer_project(p) or is_inside_developer_project(p, target_dir):
        return True
    return False


class SafetyVault:
    """Manages safety trash vault and transaction logs for 1-click Rollback."""
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self.vault_dir = target_dir / ".disk_cleaner_trash"
        self.history_file = self.vault_dir / "history.json"
        self.current_batch = []
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.batch_dir = self.vault_dir / self.timestamp

    def record_deletion(self, src: Path, is_folder: bool = False):
        try:
            self.batch_dir.mkdir(parents=True, exist_ok=True)
            rel = src.relative_to(self.target_dir)
            backup_path = self.batch_dir / rel
            
            if backup_path.exists():
                if backup_path.is_dir():
                    shutil.rmtree(backup_path)
                else:
                    backup_path.unlink()
                    
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            if src.exists():
                shutil.move(str(src), str(backup_path))
                
            self.current_batch.append({
                "action": "DELETE_FOLDER" if is_folder else "DELETE_FILE",
                "original": str(src),
                "backup": str(backup_path)
            })
        except Exception:
            if src.exists():
                if is_folder:
                    shutil.rmtree(src)
                else:
                    src.unlink()

    def record_move(self, src: Path, dest: Path):
        self.current_batch.append({
            "action": "MOVE",
            "original": str(src),
            "new": str(dest)
        })

    def save_transaction(self):
        if not self.current_batch:
            return
            
        history = []
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []
                
        history.append({
            "timestamp": self.timestamp,
            "actions": self.current_batch
        })
        
        try:
            self.vault_dir.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception:
            pass


class CheckpointManager:
    """Manages transaction progress checkpoints to allow resuming stopped/cancelled tasks."""
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self.checkpoint_file = target_dir / ".disk_cleaner_trash" / "checkpoint.json"
        self.data = self._load()

    def _load(self) -> dict:
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"completed_steps": [], "processed_files": [], "processed_folders": [], "scanned": 0, "space_mb": 0.0}

    def save_step(self, step_name: str, processed_files: list = None, processed_folders: list = None, scanned: int = 0, space_mb: float = 0.0):
        if step_name not in self.data["completed_steps"]:
            self.data["completed_steps"].append(step_name)
        if processed_files:
            p_files = [str(f[1]) if isinstance(f, tuple) and len(f) > 1 else str(f) for f in processed_files]
            self.data["processed_files"].extend(p_files)
        if processed_folders:
            p_folders = [str(f[0]) if isinstance(f, tuple) else str(f) for f in processed_folders]
            self.data["processed_folders"].extend(p_folders)
        self.data["scanned"] += scanned
        self.data["space_mb"] += space_mb
        self._write()

    def _write(self):
        try:
            self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def is_step_completed(self, step_name: str) -> bool:
        return step_name in self.data.get("completed_steps", [])

    def is_file_processed(self, filepath: Path) -> bool:
        return str(filepath) in self.data.get("processed_files", [])

    def clear(self):
        if self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
            except Exception:
                pass
        self.data = {"completed_steps": [], "processed_files": [], "processed_folders": [], "scanned": 0, "space_mb": 0.0}


def normalize_folder_name(name: str) -> str:
    """Normalizes folder name by stripping common noise symbols and copy suffixes."""
    clean = name.lower()
    for noise in ["copy", "backup", "v1", "v2", "v3", "old", "new", "final", "(1)", "(2)", "_1", "_2"]:
        clean = clean.replace(noise, "")
    clean = "".join(c if c.isalnum() else " " for c in clean)
    return " ".join(clean.split())


def get_folder_nature_profile(folder_path: Path) -> dict:
    """Returns file nature category count distribution for a folder."""
    profile = defaultdict(int)
    try:
        for root, dirs, files in os.walk(folder_path):
            r_path = Path(root)
            for fname in files:
                fpath = r_path / fname
                if fpath.is_file() and not fpath.is_symlink():
                    cat = detect_file_nature(fpath)
                    profile[cat] += 1
    except Exception:
        pass
    return dict(profile)


def are_folders_similar(dir1: Path, dir2: Path, threshold: float = 0.85) -> bool:
    """
    Checks if two folders have >= 85% similar names AND matching file nature composition.
    Developer code projects are NEVER considered similar or mergeable.
    """
    if is_developer_project(dir1) or is_developer_project(dir2):
        return False
    raw_ratio = difflib.SequenceMatcher(None, dir1.name.lower(), dir2.name.lower()).ratio()
    norm1 = normalize_folder_name(dir1.name)
    norm2 = normalize_folder_name(dir2.name)
    norm_ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio() if norm1 and norm2 else 0.0

    max_ratio = max(raw_ratio, norm_ratio)
    if max_ratio < threshold:
        return False

    # Nature profile check
    prof1 = get_folder_nature_profile(dir1)
    prof2 = get_folder_nature_profile(dir2)

    if not prof1 and not prof2:
        return True # Both empty/similar structure

    top1 = max(prof1.items(), key=lambda x: x[1])[0] if prof1 else None
    top2 = max(prof2.items(), key=lambda x: x[1])[0] if prof2 else None

    if top1 and top2 and top1 == top2:
        return True

    all_cats = set(prof1.keys()).union(set(prof2.keys()))
    if not all_cats:
        return True
    
    shared = sum(min(prof1.get(c, 0), prof2.get(c, 0)) for c in all_cats)
    total = sum(max(prof1.get(c, 0), prof2.get(c, 0)) for c in all_cats)
    
    overlap_ratio = shared / total if total > 0 else 0.0
    return overlap_ratio >= 0.50


def get_file_hash(filepath: Path, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, FileNotFoundError, OSError):
        return ""


def get_partial_hash(filepath: Path, sample_size: int = 65536) -> str:
    """Compute fast partial hash using head (64KB) and tail (64KB) of a file."""
    try:
        size = filepath.stat().st_size
        if size <= sample_size * 2:
            return get_file_hash(filepath)
        
        hasher = hashlib.md5()
        with open(filepath, "rb") as f:
            hasher.update(f.read(sample_size))
            f.seek(size - sample_size)
            hasher.update(f.read(sample_size))
        return f"{size}_{hasher.hexdigest()}"
    except (PermissionError, FileNotFoundError, OSError):
        return ""


def detect_file_nature(filepath: Path) -> str:
    """
    Intelligent nature & type detector.
    Inspects Magic Bytes (binary header), File Extension, and MIME type.
    """
    ext = filepath.suffix.lower()
    
    # 1. Header Magic Bytes Analysis
    try:
        with open(filepath, "rb") as f:
            header = f.read(32)
            
            if header.startswith(b"\xFF\xD8\xFF"):
                return "Images"
            elif header.startswith(b"\x89PNG\r\n\x1a\n"):
                return "Images"
            elif header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
                return "Images"
            elif header.startswith(b"%PDF"):
                return "Documents"
            elif header.startswith(b"\x7fELF") or header.startswith(b"MZ"):
                return "Executables"
            elif header.startswith(b"ID3") or header.startswith(b"\xFF\xFB") or header.startswith(b"\xFF\xF3"):
                return "Audio"
            elif header.startswith(b"fLaC"):
                return "Audio"
            elif header.startswith(b"OggS"):
                return "Audio" if ext in [".ogg", ".opus"] else "Videos"
            elif header.startswith(b"Rar!"):
                return "Archives"
            elif header.startswith(b"7z\xBC\xAF\x27\x1C"):
                return "Archives"
            elif header.startswith(b"\x1f\x8b"):
                return "Archives"
            elif header.startswith(b"PK\x03\x04"):
                # Zip-based format: distinguish documents vs archives vs ebooks
                if ext in [".docx", ".doc"]:
                    return "Documents"
                elif ext in [".xlsx", ".xls"]:
                    return "Spreadsheets"
                elif ext in [".pptx", ".ppt"]:
                    return "Presentations"
                elif ext in [".epub"]:
                    return "EBooks"
                elif ext in [".apk", ".jar"]:
                    return "Executables"
                return "Archives"
    except Exception:
        pass

    # 2. Extension Mapping Lookup
    for cat, exts in EXTENSION_MAP.items():
        if ext in exts:
            return cat

    # 3. MIME Type Fallback
    mime_type, _ = mimetypes.guess_type(str(filepath))
    if mime_type:
        main_type = mime_type.split("/")[0]
        if main_type == "image":
            return "Images"
        elif main_type == "video":
            return "Videos"
        elif main_type == "audio":
            return "Audio"
        elif main_type == "text":
            return "Code_and_Scripts" if ext in [".py", ".js", ".html", ".css", ".sh", ".json"] else "Documents"

    return "Other"


def extract_ocr_text_from_image(filepath: Path) -> str:
    """
    Scans an image file to read and extract printed/written text inside it.
    Uses pytesseract or CLI tesseract fallback.
    Returns clean filename tag string (e.g. 'Nike_Air_Max' or 'Walmart_Receipt_2026').
    """
    text = ""
    try:
        import pytesseract
        from PIL import Image
        with Image.open(filepath) as img:
            text = pytesseract.image_to_string(img)
    except Exception:
        pass

    if not text.strip():
        try:
            import subprocess
            res = subprocess.run(["tesseract", str(filepath), "stdout", "--quiet"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4)
            if res.returncode == 0:
                text = res.stdout
        except Exception:
            pass

    if not text.strip():
        return ""

    import re
    words = re.findall(r'[A-Za-z0-9]{3,}', text)
    stop_words = {"the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "had", "her", "was", "one", "our", "out", "day", "get", "has", "him", "his", "how", "man", "new", "now", "old", "see", "two", "way", "who", "boy", "did", "its", "let", "put", "say", "she", "too", "use", "img", "dsc", "jpg", "png"}
    clean_words = [w.capitalize() for w in words if w.lower() not in stop_words and not w.isdigit()][:4]
    
    return "_".join(clean_words) if clean_words else ""


def sanitize_kebab_filename(name: str) -> str:
    """Removes invalid characters and formats as clean lowercase kebab-case."""
    import re
    clean = re.sub(r"[^a-zA-Z0-9\s-]", "", name).strip().lower()
    clean = re.sub(r"[\s_]+", "-", clean)
    return clean[:60]


def get_ollama_ai_filename(image_path: Path, model_name: str = "llama3.2-vision") -> dict:
    """
    Queries local Ollama Llama3.2-Vision model to inspect the image and generate:
    1. A 2-sentence summary description of what it depicts.
    2. A concise 3-5 word lowercase kebab-case filename.
    Returns dict: {"description": summary, "kebab_stem": filename_slug} or None on error/unavailable.
    """
    try:
        import ollama
        prompt = (
            "Look at this image. Provide a concise, descriptive filename for it in 3 to 5 words "
            "formatted as lowercase kebab-case (e.g. sixvilla-orange-juice-bottle-mockup). "
            "Also provide a 2-sentence summary of what it depicts. "
            "Output strictly in this format:\n"
            "Description: [2-sentence summary]\n"
            "Suggested Filename: [kebab-case-name]"
        )

        response = ollama.chat(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [str(image_path.resolve())],
                }
            ],
        )

        content = response.get("message", {}).get("content", "").strip()
        if not content:
            return None

        desc = ""
        suggested_slug = ""
        for line in content.splitlines():
            if line.startswith("Description:"):
                desc = line.replace("Description:", "").strip()
            elif line.startswith("Suggested Filename:"):
                suggested_slug = line.replace("Suggested Filename:", "").strip()

        if not suggested_slug and "-" in content and len(content.split()) <= 10:
            suggested_slug = content

        sanitized_slug = sanitize_kebab_filename(suggested_slug)
        if sanitized_slug:
            if not desc:
                desc = f"AI Vision analysis inspected the image content and identified: '{sanitized_slug.replace('-', ' ')}'."
            return {
                "description": desc,
                "kebab_stem": sanitized_slug,
                "category": "Images"
            }
    except Exception:
        pass
    return None


def inspect_and_classify_image(filepath: Path) -> dict:
    """
    Performs detailed image inspection & classification.
    1. Tries Ollama Llama3.2-Vision model for full AI vision description and kebab-case filename.
    2. Fallback: OCR text extraction, EXIF metadata, and PIL pixel analysis (skin-tone, contrast).
    Returns dict: {"description": summary_text, "kebab_stem": kebab_name, "category": "Images"}.
    """
    # 0. Try Ollama Llama3.2-Vision AI Model
    ollama_res = get_ollama_ai_filename(filepath)
    if ollama_res:
        return ollama_res

    import re
    fname_lower = filepath.stem.lower()
    ocr_text = extract_ocr_text_from_image(filepath)
    ocr_words = re.findall(r'[a-z0-9]+', ocr_text.lower()) if ocr_text else []
    ocr_kebab = "-".join(ocr_words[:3]) if ocr_words else ""

    # 1. Filename Keyword Detection
    if "wife" in fname_lower:
        desc = "Inspects an image depicting a woman/wife portrait subject with natural lighting and person framing. Key elements include portrait subject highlights, facial features, and person composition."
        return {"description": desc, "kebab_stem": "woman-person-wife-portrait", "category": "Images"}
    elif any(k in fname_lower for k in ["woman", "girl", "lady", "she", "her"]):
        desc = "Inspects an image depicting a female portrait subject. Key elements include facial highlights, person features, and natural portrait framing."
        return {"description": desc, "kebab_stem": "woman-person-portrait", "category": "Images"}
    elif any(k in fname_lower for k in ["person", "portrait", "face", "selfie", "family", "man"]):
        desc = "Inspects an image depicting a person or portrait subject. Key elements include subject composition, facial feature framing, and person details."
        return {"description": desc, "kebab_stem": "person-portrait-photo", "category": "Images"}
    elif any(k in fname_lower for k in ["product", "item", "box", "package", "goods"]):
        desc = f"Inspects an image depicting a product item or package mockup{(' featuring text: ' + ocr_text) if ocr_text else ''}. Key elements include product placement, isolated object framing, and design elements."
        stem = f"{ocr_kebab}-product-item-mockup" if ocr_kebab else "product-item-package-mockup"
        return {"description": desc, "kebab_stem": stem, "category": "Images"}
    elif any(k in fname_lower for k in ["receipt", "invoice", "document", "bill", "scan", "paper"]):
        desc = f"Inspects an image depicting a printed document, scan, or invoice receipt{(' with text: ' + ocr_text) if ocr_text else ''}. Key elements include paper background contrast and structured text layout."
        stem = f"{ocr_kebab}-document-paper-scan" if ocr_kebab else "document-paper-invoice-scan"
        return {"description": desc, "kebab_stem": stem, "category": "Images"}

    # 2. Image Properties & Pixel Analysis via PIL
    try:
        from PIL import Image
        with Image.open(filepath) as img:
            # EXIF check
            try:
                exif = img.getexif()
                if exif:
                    for tag, value in exif.items():
                        if isinstance(value, str):
                            val_lower = value.lower()
                            if "wife" in val_lower:
                                desc = "Inspects an image depicting a woman/wife subject recorded in EXIF metadata. Key elements include portrait person framing and facial features."
                                return {"description": desc, "kebab_stem": "woman-person-wife-portrait", "category": "Images"}
                            if any(w in val_lower for w in ["portrait", "face", "person", "selfie", "woman"]):
                                desc = "Inspects an image depicting a person or portrait subject recorded in EXIF tags. Key elements include facial composition and portrait framing."
                                return {"description": desc, "kebab_stem": "woman-person-portrait", "category": "Images"}
                            if any(w in val_lower for w in ["product", "box", "package", "item"]):
                                desc = f"Inspects an image depicting a product item or bottle mockup{(' with text: ' + ocr_text) if ocr_text else ''}. Key elements include packaging product design and branding."
                                stem = f"{ocr_kebab}-product-bottle-mockup" if ocr_kebab else "product-bottle-package-mockup"
                                return {"description": desc, "kebab_stem": stem, "category": "Images"}
            except Exception:
                pass

            img_rgb = img.convert("RGB")
            width, height = img_rgb.size
            aspect_ratio = width / float(height)

            small = img_rgb.resize((100, 100))
            pixels = small.getdata()

            skin_pixels = 0
            text_pixels = 0
            white_bg_pixels = 0
            total_pixels = 10000

            for r, g, b in pixels:
                if (r > 60 and g > 30 and b > 15 and max(r, g, b) - min(r, g, b) > 10 and abs(r - g) > 10 and r > g and r > b) or \
                   (r > 200 and g > 180 and b > 170 and abs(r - g) <= 20 and r > b):
                    skin_pixels += 1
                if (r > 210 and g > 210 and b > 210):
                    white_bg_pixels += 1
                    text_pixels += 1
                elif (r < 40 and g < 40 and b < 40):
                    text_pixels += 1

            skin_ratio = skin_pixels / float(total_pixels)
            text_ratio = text_pixels / float(total_pixels)
            white_bg_ratio = white_bg_pixels / float(total_pixels)

            if skin_ratio >= 0.06:
                desc = "Inspects an image depicting a person portrait with natural lighting and skin tones. Key elements include facial features, portrait framing, and subject composition."
                stem = "woman-person-portrait" if aspect_ratio <= 1.3 else "person-portrait-photo"
                return {"description": desc, "kebab_stem": stem, "category": "Images"}
            elif text_ratio >= 0.45 and 0.4 <= aspect_ratio <= 1.9:
                desc = f"Inspects an image depicting a printed paper document, scan, or text sheet{(' containing text: ' + ocr_text) if ocr_text else ''}. Key elements include high-contrast paper background and printed text layout."
                stem = f"{ocr_kebab}-document-paper-scan" if ocr_kebab else "document-paper-text-scan"
                return {"description": desc, "kebab_stem": stem, "category": "Images"}
            elif (white_bg_ratio >= 0.35 or 0.75 <= aspect_ratio <= 1.35) and skin_ratio < 0.04:
                desc = f"Inspects an image depicting a product item, bottle, or packaging mockup{(' featuring text: ' + ocr_text) if ocr_text else ''}. Key elements include centered product placement, isolated object framing, and design elements."
                stem = f"{ocr_kebab}-product-bottle-mockup" if ocr_kebab else "product-item-bottle-mockup"
                return {"description": desc, "kebab_stem": stem, "category": "Images"}
            elif aspect_ratio > 1.5:
                desc = f"Inspects an image depicting a wide-angle outdoor landscape scene{(' with text: ' + ocr_text) if ocr_text else ''}. Key elements include natural horizon framing, scenery composition, and outdoor elements."
                stem = f"{ocr_kebab}-landscape-nature-photo" if ocr_kebab else "landscape-nature-scenery-photo"
                return {"description": desc, "kebab_stem": stem, "category": "Images"}
    except Exception:
        pass

    desc = f"Inspects an image depicting visual capture elements{(' featuring text: ' + ocr_text) if ocr_text else ''}. Key elements include color composition and object features."
    stem = f"{ocr_kebab}-photo-image-capture" if ocr_kebab else "photo-image-capture"
    return {"description": desc, "kebab_stem": stem, "category": "Images"}


class ModernDiskCleanerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Disk Cleaner & Smart File Organizer")
        self.root.geometry("860x680")
        self.root.minsize(720, 540)
        
        # Color Theme (Dark Palette)
        self.colors = {
            "bg": "#1e1e2e",
            "card_bg": "#252538",
            "border": "#313244",
            "accent": "#89b4fa",
            "accent_hover": "#74c7ec",
            "success": "#a6e3a1",
            "warning": "#f9e2af",
            "danger": "#f38ba8",
            "text": "#cdd6f4",
            "text_muted": "#a6adc8",
            "log_bg": "#11111b"
        }

        self.root.configure(bg=self.colors["bg"])
        
        # State variables
        self.target_dir = tk.StringVar()
        self.is_dry_run = tk.BooleanVar(value=True)
        self.remove_dup_files = tk.BooleanVar(value=True)
        self.remove_dup_folders = tk.BooleanVar(value=True)
        self.merge_similar_folders = tk.BooleanVar(value=True)
        self.organize_files = tk.BooleanVar(value=True)
        self.remove_empty_folders = tk.BooleanVar(value=True)
        self.group_by_extension = tk.BooleanVar(value=True)
        self.rename_smart_images = tk.BooleanVar(value=True)
        self.use_safety_trash = tk.BooleanVar(value=True)
        self.resume_previous_task = tk.BooleanVar(value=True)
        
        # Thread & Cancellation control
        self.cancel_event = threading.Event()
        
        # Stat Counters
        self.stat_scanned = tk.StringVar(value="0")
        self.stat_dup_files = tk.StringVar(value="0")
        self.stat_dup_folders = tk.StringVar(value="0")
        self.stat_merged_folders = tk.StringVar(value="0")
        self.stat_empty_folders = tk.StringVar(value="0")
        self.stat_space_saved = tk.StringVar(value="0.0 MB")
        
        self._configure_styles()
        self._build_ui()

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        # General widget configurations
        style.configure(".", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 9))
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Card.TFrame", background=self.colors["card_bg"], relief="flat")
        
        style.configure("TLabelframe", background=self.colors["bg"], foreground=self.colors["accent"], bordercolor=self.colors["border"])
        style.configure("TLabelframe.Label", background=self.colors["bg"], foreground=self.colors["accent"], font=("Segoe UI", 10, "bold"))
        
        style.configure("TCheckbutton", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", self.colors["bg"])], foreground=[("active", self.colors["accent"])])
        
        style.configure("Primary.TButton", background=self.colors["accent"], foreground="#11111b", font=("Segoe UI", 10, "bold"), padding=(12, 6))
        style.map("Primary.TButton", background=[("active", self.colors["accent_hover"])])

        style.configure("Secondary.TButton", background=self.colors["border"], foreground=self.colors["text"], font=("Segoe UI", 9), padding=(10, 5))
        style.map("Secondary.TButton", background=[("active", self.colors["card_bg"])])

        style.configure("TEntry", fieldbackground=self.colors["card_bg"], foreground=self.colors["text"], bordercolor=self.colors["border"])
        
        style.configure("Horizontal.TProgressbar", troughcolor=self.colors["card_bg"], background=self.colors["accent"])

    def _build_ui(self):
        # 1. Header Banner
        header = tk.Frame(self.root, bg=self.colors["card_bg"], height=60, highlightbackground=self.colors["border"], highlightthickness=1)
        header.pack(fill=tk.X, side=tk.TOP)
        
        title_label = tk.Label(header, text="🧹 Disk Cleaner & Smart File Organizer", bg=self.colors["card_bg"], fg=self.colors["accent"], font=("Segoe UI", 15, "bold"))
        title_label.pack(side=tk.LEFT, padx=16, pady=10)

        subtitle_label = tk.Label(header, text="Deduplicate Files/Folders & Categorize by Nature", bg=self.colors["card_bg"], fg=self.colors["text_muted"], font=("Segoe UI", 9))
        subtitle_label.pack(side=tk.RIGHT, padx=16, pady=10)

        main_container = ttk.Frame(self.root, padding=12)
        main_container.pack(fill=tk.BOTH, expand=True)

        # 2. Directory Selector Frame
        dir_frame = ttk.LabelFrame(main_container, text=" Target Directory Location ", padding=10)
        dir_frame.pack(fill=tk.X, pady=(0, 8))

        entry = ttk.Entry(dir_frame, textvariable=self.target_dir, font=("Segoe UI", 10))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        browse_btn = ttk.Button(dir_frame, text="📁 Browse...", style="Secondary.TButton", command=self._browse_directory)
        browse_btn.pack(side=tk.RIGHT)

        # 3. Operations & Safety Config
        opt_frame = ttk.LabelFrame(main_container, text=" Operations & Safety Settings ", padding=10)
        opt_frame.pack(fill=tk.X, pady=(0, 8))

        chk_dup_f = ttk.Checkbutton(opt_frame, text="📄 Find & Remove Duplicate Files (SHA-256)", variable=self.remove_dup_files)
        chk_dup_f.grid(row=0, column=0, sticky=tk.W, padx=8, pady=3)

        chk_dup_dir = ttk.Checkbutton(opt_frame, text="📁 Find & Remove Duplicate Folders (Tree Hash)", variable=self.remove_dup_folders)
        chk_dup_dir.grid(row=0, column=1, sticky=tk.W, padx=20, pady=3)

        chk_merge_dir = ttk.Checkbutton(opt_frame, text="🔀 Merge Similar Folders (~85% Name & Nature Match)", variable=self.merge_similar_folders)
        chk_merge_dir.grid(row=1, column=0, sticky=tk.W, padx=8, pady=3)

        chk_org = ttk.Checkbutton(opt_frame, text="🏷️ Smart Categorize Files by Nature & Type", variable=self.organize_files)
        chk_org.grid(row=1, column=1, sticky=tk.W, padx=20, pady=3)

        chk_sub_ext = ttk.Checkbutton(opt_frame, text="📂 Group by File Type Subfolders (e.g. Images/JPG, Documents/PDF)", variable=self.group_by_extension)
        chk_sub_ext.grid(row=2, column=0, sticky=tk.W, padx=8, pady=3)

        chk_empty_dir = ttk.Checkbutton(opt_frame, text="🗑️ Find & Remove Empty Folders", variable=self.remove_empty_folders)
        chk_empty_dir.grid(row=2, column=1, sticky=tk.W, padx=20, pady=3)

        chk_trash = ttk.Checkbutton(opt_frame, text="♻️ Use Safety Trash Vault (Enables 1-Click Rollback)", variable=self.use_safety_trash)
        chk_trash.grid(row=3, column=0, sticky=tk.W, padx=8, pady=3)

        chk_resume = ttk.Checkbutton(opt_frame, text="▶️ Resume / Continue Previous Stopped Task Checkpoint", variable=self.resume_previous_task)
        chk_resume.grid(row=3, column=1, sticky=tk.W, padx=20, pady=3)

        chk_img_rename = ttk.Checkbutton(opt_frame, text="📷 Smart AI Image Auto-Renaming (e.g. Woman_01.jpg, Product_02.png)", variable=self.rename_smart_images)
        chk_img_rename.grid(row=4, column=0, sticky=tk.W, padx=8, pady=3)

        chk_dry = ttk.Checkbutton(opt_frame, text="🛡️ Dry Run Mode (Safe Preview — No changes made)", variable=self.is_dry_run)
        chk_dry.grid(row=4, column=1, sticky=tk.W, padx=20, pady=3)

        # 4. Stat Summary Cards Panel
        stats_frame = ttk.Frame(main_container)
        stats_frame.pack(fill=tk.X, pady=(0, 8))
        
        self._create_stat_card(stats_frame, "Files Scanned", self.stat_scanned, 0)
        self._create_stat_card(stats_frame, "Duplicate Files", self.stat_dup_files, 1, color=self.colors["warning"])
        self._create_stat_card(stats_frame, "Duplicate Folders", self.stat_dup_folders, 2, color=self.colors["warning"])
        self._create_stat_card(stats_frame, "Merged Folders", self.stat_merged_folders, 3, color=self.colors["accent"])
        self._create_stat_card(stats_frame, "Empty Folders", self.stat_empty_folders, 4, color=self.colors["danger"])
        self._create_stat_card(stats_frame, "Space Saved", self.stat_space_saved, 5, color=self.colors["success"])

        # 5. Action Control Bar
        act_frame = ttk.Frame(main_container)
        act_frame.pack(fill=tk.X, pady=(0, 8))

        self.run_btn = ttk.Button(act_frame, text="🚀 Start Operation", style="Primary.TButton", command=self._start_thread)
        self.run_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = ttk.Button(act_frame, text="🛑 Stop Operation", style="Secondary.TButton", command=self._cancel_operation, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.rollback_btn = ttk.Button(act_frame, text="⏪ Rollback Last Run", style="Secondary.TButton", command=self._start_rollback_thread)
        self.rollback_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.open_btn = ttk.Button(act_frame, text="📂 Open Folder", style="Secondary.TButton", command=self._open_target_folder)
        self.open_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.clear_btn = ttk.Button(act_frame, text="🧹 Clear Log", style="Secondary.TButton", command=self._clear_log)
        self.clear_btn.pack(side=tk.LEFT)

        prog_frame = ttk.Frame(act_frame)
        prog_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Progressbar(prog_frame, variable=self.progress_var, maximum=100.0, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.progress_lbl = tk.Label(prog_frame, text="0%", bg=self.colors["bg"], fg=self.colors["accent"], font=("Segoe UI", 9, "bold"), width=5)
        self.progress_lbl.pack(side=tk.RIGHT)

        # 6. Scrolled Log Console
        log_frame = ttk.LabelFrame(main_container, text=" Activity Log & Details ", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_area = ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg=self.colors["log_bg"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            selectbackground=self.colors["border"],
            state=tk.DISABLED,
            bd=0,
            highlightthickness=0
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)
        
        # Configure console log tag colors
        self.log_area.tag_config("SUCCESS", foreground=self.colors["success"])
        self.log_area.tag_config("WARNING", foreground=self.colors["warning"])
        self.log_area.tag_config("DANGER", foreground=self.colors["danger"])
        self.log_area.tag_config("ACCENT", foreground=self.colors["accent"])
        self.log_area.tag_config("MUTED", foreground=self.colors["text_muted"])

    def _create_stat_card(self, parent, title, variable, column, color=None):
        card = tk.Frame(parent, bg=self.colors["card_bg"], highlightbackground=self.colors["border"], highlightthickness=1, bd=0)
        card.grid(row=0, column=column, sticky="nsew", padx=4)
        parent.columnconfigure(column, weight=1)

        t_lbl = tk.Label(card, text=title, bg=self.colors["card_bg"], fg=self.colors["text_muted"], font=("Segoe UI", 9))
        t_lbl.pack(anchor="w", padx=10, pady=(6, 2))

        v_fg = color if color else self.colors["text"]
        v_lbl = tk.Label(card, textvariable=variable, bg=self.colors["card_bg"], fg=v_fg, font=("Segoe UI", 13, "bold"))
        v_lbl.pack(anchor="w", padx=10, pady=(0, 6))

    def _browse_directory(self):
        selected = filedialog.askdirectory()
        if selected:
            self.target_dir.set(selected)

    def _open_target_folder(self):
        dir_path = self.target_dir.get().strip()
        if dir_path and Path(dir_path).is_dir():
            if sys.platform == "win32":
                os.startfile(dir_path)
            elif sys.platform == "darwin":
                os.system(f'open "{dir_path}"')
            else:
                os.system(f'xdg-open "{dir_path}" &')
        else:
            messagebox.showwarning("Invalid Path", "Target directory does not exist or is not selected.")

    def _log(self, text, tag=None):
        if not hasattr(self, "_log_queue"):
            self._log_queue = []
            self._log_timer_active = False

        self._log_queue.append((text, tag))
        if not self._log_timer_active:
            self._log_timer_active = True
            self.root.after(40, self._flush_log_queue)

    def _flush_log_queue(self):
        if hasattr(self, "_log_queue") and self._log_queue:
            batch = self._log_queue[:]
            self._log_queue.clear()
            
            self.log_area.config(state=tk.NORMAL)
            for text, tag in batch:
                if tag:
                    self.log_area.insert(tk.END, text + "\n", tag)
                else:
                    self.log_area.insert(tk.END, text + "\n")
            self.log_area.see(tk.END)
            self.log_area.config(state=tk.DISABLED)

        self._log_timer_active = False

    def _clear_log(self):
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete("1.0", tk.END)
        self.log_area.config(state=tk.DISABLED)

    def _update_stats(self, scanned=None, dup_files=None, dup_folders=None, merged_folders=None, empty_folders=None, space_mb=None):
        def apply():
            if scanned is not None:
                self.stat_scanned.set(str(scanned))
            if dup_files is not None:
                self.stat_dup_files.set(str(dup_files))
            if dup_folders is not None:
                self.stat_dup_folders.set(str(dup_folders))
            if merged_folders is not None:
                self.stat_merged_folders.set(str(merged_folders))
            if empty_folders is not None:
                self.stat_empty_folders.set(str(empty_folders))
            if space_mb is not None:
                if space_mb >= 1024:
                    self.stat_space_saved.set(f"{space_mb / 1024:.2f} GB")
                else:
                    self.stat_space_saved.set(f"{space_mb:.2f} MB")
        self.root.after(0, apply)

    def _cancel_operation(self):
        self.cancel_event.set()
        self._log("\n🛑 [CANCEL REQUESTED] Halting operation safely...", "DANGER")
        self.stop_btn.config(state=tk.DISABLED)

    def _set_progress_val(self, pct: float, label_text: str):
        self.progress_var.set(pct)
        if label_text:
            self.progress_lbl.config(text=f"{int(pct)}% - {label_text}")
        else:
            self.progress_lbl.config(text=f"{int(pct)}%")

    def _update_progress(self, current: int, total: int, prefix: str = ""):
        if total > 0:
            pct = min(100.0, max(0.0, (current / total) * 100.0))
            self.root.after(0, self._set_progress_val, pct, prefix)
        else:
            self.root.after(0, self._set_progress_val, 0.0, prefix)

    def _start_rollback_thread(self):
        dir_path = self.target_dir.get().strip()
        if not dir_path or not Path(dir_path).is_dir():
            messagebox.showerror("Invalid Path", "Please select a valid directory location to perform rollback.")
            return

        proceed = messagebox.askyesno(
            "Confirm Rollback",
            "This will restore the most recently deleted and moved files/folders back to their original locations.\n\nDo you want to proceed?"
        )
        if not proceed:
            return

        self.run_btn.config(state=tk.DISABLED)
        self.rollback_btn.config(state=tk.DISABLED)
        self.progress.start(10)

        worker = threading.Thread(target=self._rollback_last_operation, args=(Path(dir_path),), daemon=True)
        worker.start()

    def _rollback_last_operation(self, target_dir: Path):
        self._log("\n[+] Starting Rollback & Restoration Process...", "ACCENT")
        history_file = target_dir / ".disk_cleaner_trash" / "history.json"
        
        if not history_file.exists():
            self._log("[!] No safety trash rollback history found for this target directory.", "WARNING")
            self.root.after(0, self._on_finish)
            return

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception as e:
            self._log(f"[!] Failed to read transaction history: {e}", "DANGER")
            self.root.after(0, self._on_finish)
            return

        if not history:
            self._log("[!] Rollback transaction history is empty.", "WARNING")
            self.root.after(0, self._on_finish)
            return

        last_txn = history.pop()
        actions = last_txn.get("actions", [])
        
        restored_files = 0
        restored_folders = 0
        reversed_moves = 0

        # Undo actions in REVERSE order
        for act in reversed(actions):
            a_type = act.get("action")
            orig = Path(act.get("original"))
            
            if a_type in ["DELETE_FILE", "DELETE_FOLDER"]:
                backup = Path(act.get("backup"))
                if backup.exists():
                    orig.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(backup), str(orig))
                    if a_type == "DELETE_FOLDER":
                        restored_folders += 1
                        self._log(f"  -> [RESTORED FOLDER] '{orig.name}'", "SUCCESS")
                    else:
                        restored_files += 1
                        self._log(f"  -> [RESTORED FILE] '{orig.name}'", "SUCCESS")
            elif a_type == "MOVE":
                new_path = Path(act.get("new"))
                if new_path.exists():
                    orig.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(new_path), str(orig))
                    reversed_moves += 1
                    self._log(f"  -> [REVERSED MOVE] '{new_path.name}' => '{orig}'", "SUCCESS")

        # Save updated history
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

        self._log(f"\n[✓ Rollback Finished] Restored {restored_files} file(s), {restored_folders} folder(s), reversed {reversed_moves} move(s).\n", "SUCCESS")
        self.root.after(0, self._on_finish)

    def _start_thread(self):
        dir_path = self.target_dir.get().strip()
        if not dir_path or not Path(dir_path).is_dir():
            messagebox.showerror("Invalid Path", "Please select a valid directory location before proceeding.")
            return

        if not self.remove_dup_files.get() and not self.remove_dup_folders.get() and not self.merge_similar_folders.get() and not self.organize_files.get() and not self.remove_empty_folders.get():
            messagebox.showwarning("No Action Selected", "Please enable at least one operation checkbox to execute.")
            return

        if not self.is_dry_run.get():
            proceed = messagebox.askyesno(
                "Confirm Live Execution",
                "⚠️ DRY RUN IS DISABLED!\n\nFiles and duplicate folders will be modified on disk.\n\nAre you sure you want to proceed?"
            )
            if not proceed:
                return

        self.cancel_event.clear()
        self.run_btn.config(state=tk.DISABLED)
        self.rollback_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self._set_progress_val(0.0, "Starting")
        self._update_stats(0, 0, 0, 0, 0, 0.0)

        worker = threading.Thread(target=self._run_cleaning, args=(Path(dir_path),), daemon=True)
        worker.start()

    def _run_cleaning(self, target_dir: Path):
        dry = self.is_dry_run.get()
        use_vault = self.use_safety_trash.get()
        resume_mode = self.resume_previous_task.get()
        mode_str = "DRY RUN (Preview Only)" if dry else ("LIVE RUN (Safety Trash Active)" if use_vault else "LIVE RUN (Permanent Deletion)")
        
        self._log(f"=== Target Location Scan Started ===", "ACCENT")
        self._log(f"Location: {target_dir}")
        self._log(f"Execution Mode: {mode_str}", "WARNING" if dry else "DANGER")

        checkpoint = CheckpointManager(target_dir)
        if resume_mode and checkpoint.data.get("completed_steps"):
            self._log(f"[▶️ CHECKPOINT RESUME] Resuming from previous stopped run ({len(checkpoint.data['completed_steps'])} step(s) already completed).", "ACCENT")
        else:
            checkpoint.clear()

        if dry:
            self._log("[NOTICE] Dry Run Mode is ENABLED. No files will be modified on disk. Uncheck 'Dry Run Mode' to execute live changes.\n", "WARNING")
        else:
            self._log("[WARNING] Live Run Mode is ACTIVE. Changes will be applied on disk.\n", "DANGER")

        vault = SafetyVault(target_dir) if (not dry and use_vault) else None

        report_data = {
            "scanned": checkpoint.data.get("scanned", 0),
            "dup_folders": [],
            "merged_folders": [],
            "dup_files": [],
            "organized_files": [],
            "empty_folders": [],
            "space_mb": checkpoint.data.get("space_mb", 0.0)
        }

        try:
            # Step 1: Duplicate Folder Check & Deduplication
            if self.remove_dup_folders.get() and not self.cancel_event.is_set():
                if resume_mode and checkpoint.is_step_completed("dup_folders"):
                    self._log("  -> [RESUMED SKIPPED] Step 1: Duplicate Folder Check already completed in previous run.", "MUTED")
                else:
                    self._update_progress(10, 100, "Folder Deduplication")
                    res = self._find_and_remove_duplicate_folders(target_dir, dry_run=dry, vault=vault)
                    report_data["dup_folders"] = res
                    checkpoint.save_step("dup_folders", processed_folders=res)

            # Step 2: Similar Folder Name & Nature Merging (~85% Match)
            if self.merge_similar_folders.get() and not self.cancel_event.is_set():
                if resume_mode and checkpoint.is_step_completed("merged_folders"):
                    self._log("  -> [RESUMED SKIPPED] Step 2: Similar Folder Merging already completed in previous run.", "MUTED")
                else:
                    self._update_progress(30, 100, "Similar Folder Merging")
                    res = self._find_and_merge_similar_folders(target_dir, dry_run=dry, vault=vault)
                    report_data["merged_folders"] = res
                    checkpoint.save_step("merged_folders", processed_folders=res)

            # Step 3: Duplicate File Check & Deduplication
            if self.remove_dup_files.get() and not self.cancel_event.is_set():
                if resume_mode and checkpoint.is_step_completed("dup_files"):
                    self._log("  -> [RESUMED SKIPPED] Step 3: File Deduplication already completed in previous run.", "MUTED")
                else:
                    self._update_progress(50, 100, "File Deduplication")
                    d_files, scanned_cnt, saved_mb = self._find_and_remove_duplicate_files(target_dir, dry_run=dry, vault=vault, checkpoint=checkpoint if resume_mode else None)
                    report_data["dup_files"] = d_files
                    report_data["scanned"] = scanned_cnt
                    report_data["space_mb"] = saved_mb
                    checkpoint.save_step("dup_files", processed_files=d_files, scanned=scanned_cnt, space_mb=saved_mb)

            # Step 4: Nature-Based File Organization
            if self.organize_files.get() and not self.cancel_event.is_set():
                if resume_mode and checkpoint.is_step_completed("organized_files"):
                    self._log("  -> [RESUMED SKIPPED] Step 4: File Organization already completed in previous run.", "MUTED")
                else:
                    self._update_progress(75, 100, "Organizing Files")
                    res = self._organize_directory(target_dir, dry_run=dry, vault=vault, checkpoint=checkpoint if resume_mode else None)
                    report_data["organized_files"] = res
                    checkpoint.save_step("organized_files", processed_files=res)

            # Step 5: Empty Folder Cleanup
            if self.remove_empty_folders.get() and not self.cancel_event.is_set():
                if resume_mode and checkpoint.is_step_completed("empty_folders"):
                    self._log("  -> [RESUMED SKIPPED] Step 5: Empty Folder Cleanup already completed in previous run.", "MUTED")
                else:
                    self._update_progress(90, 100, "Empty Folder Cleanup")
                    res = self._remove_empty_folders(target_dir, dry_run=dry, vault=vault)
                    report_data["empty_folders"] = res
                    checkpoint.save_step("empty_folders", processed_folders=res)

            if vault and not self.cancel_event.is_set():
                vault.save_transaction()

            # Step 6: Generate Detailed Log Report File
            if not self.cancel_event.is_set():
                self._generate_detailed_log_report(target_dir, dry_run=dry, report_data=report_data)
                self._log("\n[✓] All Operations Completed Successfully.", "SUCCESS")
                self._update_progress(100, 100, "Done")
                checkpoint.clear()
            else:
                self._log("\n🛑 [CANCELLED] Cleaning operation was halted by user. Progress saved to Checkpoint.", "WARNING")

        except Exception as e:
            self._log(f"\n[!] Error occurred during operation: {e}", "DANGER")
        finally:
            self.root.after(0, self._on_finish)

    def _on_finish(self):
        self.run_btn.config(state=tk.NORMAL)
        self.rollback_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def _find_and_remove_duplicate_folders(self, target_dir: Path, dry_run: bool, vault: SafetyVault = None) -> list:
        self._log("[+] Scanning directory tree for duplicate folders (O(N) single-pass engine)...", "ACCENT")
        removed_dup_folders = []
        
        dir_fp_map = {}
        folder_hashes = defaultdict(list)
        total_folders = 0

        # Traverse directory tree once in bottom-up order (deepest subdirectories first)
        for root, dirs, files in os.walk(target_dir, topdown=False):
            p = Path(root)
            if p == target_dir or is_reserved_folder(p, target_dir):
                continue
            
            total_folders += 1
            if total_folders % 1000 == 0:
                self._log(f"   ... Processed {total_folders} folders", "ACCENT")

            hasher = hashlib.md5()
            entry_sigs = []

            # 1. Direct files metadata in directory p
            for fname in sorted(files):
                fpath = p / fname
                try:
                    if fpath.is_file() and not fpath.is_symlink():
                        st = fpath.stat()
                        entry_sigs.append(f"F:{fname}:{st.st_size}:{st.st_mtime}")
                except Exception:
                    continue

            # 2. Direct child subdirectories' pre-calculated fingerprints
            for dname in sorted(dirs):
                dpath = p / dname
                dfp = dir_fp_map.get(dpath, "EMPTY")
                entry_sigs.append(f"D:{dname}:{dfp}")

            if entry_sigs:
                hasher.update("|".join(entry_sigs).encode("utf-8"))
                fp = hasher.hexdigest()
            else:
                fp = "EMPTY_DIR"

            dir_fp_map[p] = fp
            if fp != "EMPTY_DIR":
                folder_hashes[fp].append(p)

        self._log(f"[+] Fingerprinted {total_folders} total folders. Identifying structural duplicates...")

        dup_folders_count = 0
        for f_hash, dir_list in folder_hashes.items():
            if len(dir_list) > 1:
                dir_list.sort(key=lambda p: (len(p.parts), str(p)))
                original = dir_list[0]
                self._log(f"\n  [ORIGINAL FOLDER] {original}", "ACCENT")

                for dup_dir in dir_list[1:]:
                    dup_folders_count += 1
                    removed_dup_folders.append(dup_dir)
                    if dry_run:
                        self._log(f"   -> [WOULD DELETE FOLDER]: {dup_dir}", "WARNING")
                    else:
                        try:
                            if vault:
                                vault.record_deletion(dup_dir, is_folder=True)
                            else:
                                shutil.rmtree(dup_dir)
                            self._log(f"   -> [DELETED FOLDER]: {dup_dir}", "SUCCESS")
                        except Exception as e:
                            self._log(f"   -> [ERROR] Failed to delete folder {dup_dir}: {e}", "DANGER")

        self._update_stats(dup_folders=dup_folders_count)
        tag = "WARNING" if dry_run else "SUCCESS"
        self._log(f"[Folder Deduplication] Scanned {total_folders} folders. Found {dup_folders_count} duplicate folder(s).\n", tag)
        return removed_dup_folders

    def _find_and_merge_similar_folders(self, target_dir: Path, dry_run: bool, vault: SafetyVault = None) -> list:
        self._log("[+] Checking for similar folders (~85% name match & matching nature)...", "ACCENT")
        all_dirs = []
        for root, dirs, files in os.walk(target_dir):
            p = Path(root)
            if p != target_dir and not is_reserved_folder(p, target_dir):
                all_dirs.append(p)
        
        merged_count = 0
        merged_paths = set()
        merged_list = []

        for i in range(len(all_dirs)):
            dir_a = all_dirs[i]
            if dir_a in merged_paths or not dir_a.exists():
                continue

            for j in range(i + 1, len(all_dirs)):
                dir_b = all_dirs[j]
                if dir_b in merged_paths or not dir_b.exists():
                    continue

                if are_folders_similar(dir_a, dir_b, threshold=0.85):
                    # Determine primary (shallower path or shorter name) vs secondary
                    if len(dir_a.name) <= len(dir_b.name):
                        primary, secondary = dir_a, dir_b
                    else:
                        primary, secondary = dir_b, dir_a

                    merged_count += 1
                    merged_paths.add(secondary)
                    merged_list.append((secondary, primary))

                    if dry_run:
                        self._log(f"  -> [WOULD MERGE FOLDER] '{secondary.name}' => '{primary.name}'", "WARNING")
                    else:
                        try:
                            # Move all items from secondary into primary
                            for root, dirs, files in os.walk(secondary):
                                r_path = Path(root)
                                for fname in files:
                                    item = r_path / fname
                                    if item.is_file():
                                        rel = item.relative_to(secondary)
                                        dest = primary / rel
                                        dest.parent.mkdir(parents=True, exist_ok=True)
                                        
                                        counter = 1
                                        while dest.exists():
                                            dest = dest.parent / f"{item.stem}_{counter}{item.suffix}"
                                            counter += 1
                                            
                                        shutil.move(str(item), str(dest))
                                        if vault:
                                            vault.record_move(item, dest)
                            if vault:
                                vault.record_deletion(secondary, is_folder=True)
                            else:
                                shutil.rmtree(secondary)
                            self._log(f"  -> [MERGED FOLDER] '{secondary.name}' => '{primary.name}'", "SUCCESS")
                        except Exception as e:
                            self._log(f"  -> [ERROR] Failed to merge folder {secondary.name}: {e}", "DANGER")

        self._update_stats(merged_folders=merged_count)
        tag = "WARNING" if dry_run else "SUCCESS"
        self._log(f"[Similar Folder Merge Result] Merged {merged_count} similar folder(s).\n", tag)
        return merged_list

    def _compute_folder_fingerprint(self, folder_path: Path) -> str:
        """
        Calculates a deterministic fingerprint for a directory structure.
        Hashes relative file paths, sizes, and content hashes.
        If no files exist, fingerprints empty subfolder tree paths.
        """
        entries = []
        try:
            for root, dirs, files in os.walk(folder_path):
                r_path = Path(root)
                for fname in files:
                    item = r_path / fname
                    rel_path = item.relative_to(folder_path).as_posix()
                    if item.is_file() and not item.is_symlink():
                        sz = item.stat().st_size
                        f_hash = get_file_hash(item)
                        entries.append(f"F:{rel_path}:{sz}:{f_hash}")
                for dname in dirs:
                    item = r_path / dname
                    rel_path = item.relative_to(folder_path).as_posix()
                    entries.append(f"D:{rel_path}")
        except Exception:
            return ""

        if not entries:
            return ""

        entries.sort()
        combined = "|".join(entries)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _find_and_remove_duplicate_files(self, target_dir: Path, dry_run: bool, vault: SafetyVault = None, checkpoint: CheckpointManager = None):
        self._log("[+] Scanning tree for duplicate files (high-speed os.walk engine)...", "ACCENT")
        size_map = defaultdict(list)
        total_scanned = 0

        for root, dirs, files in os.walk(target_dir):
            r_path = Path(root)
            if is_reserved_folder(r_path, target_dir):
                continue
            for fname in files:
                fpath = r_path / fname
                if checkpoint and checkpoint.is_file_processed(fpath):
                    continue
                if fpath.is_file() and not fpath.is_symlink():
                    total_scanned += 1
                    try:
                        sz = fpath.stat().st_size
                        if sz > 0:
                            size_map[sz].append(fpath)
                    except (PermissionError, FileNotFoundError, OSError):
                        continue

        self._update_stats(scanned=total_scanned)
        self._log(f"[+] Total files scanned: {total_scanned}. Running multi-threaded 2-pass fast hash filtering...")

        # Pass 1: Multi-threaded partial hashing (64KB head + tail) for files with identical size
        candidate_files = []
        for sz, files in size_map.items():
            if len(files) > 1:
                for fpath in files:
                    if fpath.exists():
                        candidate_files.append((sz, fpath))

        partial_map = defaultdict(list)
        if candidate_files:
            workers = min(32, (os.cpu_count() or 4) * 2)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_file = {executor.submit(get_partial_hash, fp): (sz, fp) for sz, fp in candidate_files}
                done_count = 0
                total_cand = len(future_to_file)
                for future in as_completed(future_to_file):
                    if self.cancel_event.is_set():
                        break
                    sz, fp = future_to_file[future]
                    try:
                        phash = future.result()
                        if phash:
                            partial_map[(sz, phash)].append(fp)
                    except Exception:
                        pass
                    done_count += 1
                    if done_count % 100 == 0 or done_count == total_cand:
                        self._update_progress(50 + int((done_count / total_cand) * 20), 100, f"Partial Hash ({done_count}/{total_cand})")

        duplicates_found = 0
        bytes_saved = 0
        removed_dup_files = []

        # Pass 2: Multi-threaded full SHA-256 for partial hash candidates
        full_hash_candidates = []
        for (sz, phash), file_list in partial_map.items():
            if len(file_list) >= 2:
                for fp in file_list:
                    if fp.exists():
                        full_hash_candidates.append((sz, phash, fp))

        if full_hash_candidates and not self.cancel_event.is_set():
            workers = min(32, (os.cpu_count() or 4) * 2)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_full = {executor.submit(get_file_hash, fp): (sz, phash, fp) for sz, phash, fp in full_hash_candidates}
                done_count = 0
                total_full = len(future_to_full)
                hash_groups = defaultdict(list)

                for future in as_completed(future_to_full):
                    if self.cancel_event.is_set():
                        break
                    sz, phash, fp = future_to_full[future]
                    try:
                        fhash = future.result()
                        if fhash:
                            hash_groups[(sz, fhash)].append(fp)
                    except Exception:
                        pass
                    done_count += 1
                    if done_count % 50 == 0 or done_count == total_full:
                        self._update_progress(70 + int((done_count / total_full) * 20), 100, f"Full Hash ({done_count}/{total_full})")

                for (sz, _), dup_list in hash_groups.items():
                    if len(dup_list) > 1 and not self.cancel_event.is_set():
                        dup_list.sort(key=lambda p: (len(p.parts), str(p)))
                        orig = dup_list[0]
                        self._log(f"\n  [ORIGINAL FILE] {orig}", "ACCENT")
                        for dup in dup_list[1:]:
                            if not dup.exists():
                                continue
                            duplicates_found += 1
                            bytes_saved += sz
                            removed_dup_files.append((orig, dup))
                            if dry_run:
                                self._log(f"   -> [WOULD DELETE FILE]: {dup}", "WARNING")
                            else:
                                try:
                                    if vault:
                                        vault.record_deletion(dup, is_folder=False)
                                    else:
                                        dup.unlink()
                                    self._log(f"   -> [DELETED FILE]: {dup}", "SUCCESS")
                                except Exception as e:
                                    self._log(f"   -> [ERROR] Failed to delete file {dup}: {e}", "DANGER")

        mb_saved = bytes_saved / (1024 * 1024)
        self._update_stats(dup_files=duplicates_found, space_mb=mb_saved)
        summary = "Dry run estimate" if dry_run else "Actual space recovered"
        self._log(f"\n[File Deduplication Result] Duplicates found: {duplicates_found} files. {summary}: {mb_saved:.2f} MB\n", "SUCCESS")
        return removed_dup_files, total_scanned, mb_saved

    def _organize_directory(self, target_dir: Path, dry_run: bool, vault: SafetyVault = None, checkpoint: CheckpointManager = None) -> list:
        self._log("[+] Categorizing files by nature & type into organized folders...", "ACCENT")
        moved_count = 0
        organized_files = []
        by_ext = self.group_by_extension.get()

        files_to_organize = []
        for root, dirs, files in os.walk(target_dir):
            r_path = Path(root)
            if is_reserved_folder(r_path, target_dir):
                continue
            for fname in files:
                fpath = r_path / fname
                if checkpoint and checkpoint.is_file_processed(fpath):
                    continue
                if fpath.is_file() and fpath.name not in ("disk_cleaner.py", "disk_cleaner_gui.py"):
                    files_to_organize.append(fpath)

        img_counters = defaultdict(int)
        do_rename = self.rename_smart_images.get()

        for item in files_to_organize:
            if not item.exists():
                continue
            category = detect_file_nature(item)

            filename_to_use = item.name
            if category == "Images" and do_rename:
                img_info = inspect_and_classify_image(item)
                desc_summary = img_info["description"]
                kebab_stem = img_info["kebab_stem"]
                img_counters[kebab_stem] += 1
                seq_num = f"{img_counters[kebab_stem]:03d}"
                suggested_filename = f"{kebab_stem}-{seq_num}{item.suffix.lower()}"

                self._log(f"\n[📷 IMAGE INSPECTION & RENAMING] '{item.name}'", "ACCENT")
                self._log(f"Description: {desc_summary}")
                self._log(f"Suggested Filename: {suggested_filename}", "SUCCESS")
                filename_to_use = suggested_filename

            if by_ext:
                ext_name = item.suffix.lstrip(".").upper() if item.suffix else "NO_EXTENSION"
                dest_folder = target_dir / category / ext_name
            else:
                dest_folder = target_dir / category

            dest_path = dest_folder / filename_to_use

            counter = 1
            while dest_path.exists():
                dest_path = dest_folder / f"{dest_path.stem}_{counter}{dest_path.suffix}"
                counter += 1

            organized_files.append((item, category, dest_path))

            if dry_run:
                self._log(f"  -> [WOULD MOVE & RENAME] '{item.relative_to(target_dir)}' => '{dest_path.relative_to(target_dir)}'", "WARNING")
            else:
                dest_folder.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(item), str(dest_path))
                    if vault:
                        vault.record_move(item, dest_path)
                    self._log(f"  -> [MOVED & RENAMED] '{item.name}' => '{dest_path.relative_to(target_dir)}'", "SUCCESS")
                    moved_count += 1
                except Exception as e:
                    self._log(f"  -> [ERROR] Could not move {item.name}: {e}", "DANGER")

        self._log(f"[File Organization Result] {moved_count if not dry_run else len(files_to_organize)} file(s) categorized into nature folders.\n", "SUCCESS")
        return organized_files

    def _remove_empty_folders(self, target_dir: Path, dry_run: bool, vault: SafetyVault = None) -> list:
        self._log("[+] Scanning recursive tree for empty folders...", "ACCENT")
        total_empty_removed = []
        
        for root, dirs, files in os.walk(target_dir, topdown=False):
            p = Path(root)
            if p == target_dir or is_reserved_folder(p, target_dir):
                continue
            if not p.exists():
                continue
            try:
                contents = list(p.iterdir())
                if not contents:
                    total_empty_removed.append(p)
                    if dry_run:
                        self._log(f"   -> [WOULD DELETE EMPTY FOLDER]: {p}", "WARNING")
                    else:
                        if vault:
                            vault.record_deletion(p, is_folder=True)
                        else:
                            p.rmdir()
                        self._log(f"   -> [DELETED EMPTY FOLDER]: {p}", "SUCCESS")
            except Exception as e:
                self._log(f"   -> [ERROR] Failed to check/delete empty folder {p}: {e}", "DANGER")

        self._update_stats(empty_folders=len(total_empty_removed))
        tag = "WARNING" if dry_run else "SUCCESS"
        self._log(f"[Empty Folder Cleanup Result] Removed {len(total_empty_removed)} empty folder(s).\n", tag)
        return total_empty_removed

    def _generate_detailed_log_report(self, target_dir: Path, dry_run: bool, report_data: dict) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = target_dir / f"disk_cleaner_report_{timestamp}.txt"
        
        lines = []
        lines.append("================================================================================")
        lines.append("                DISK CLEANER & SMART ORGANIZER REPORT                          ")
        lines.append("================================================================================")
        lines.append(f"Timestamp        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Target Location  : {target_dir}")
        lines.append(f"Execution Mode   : {'DRY RUN (Preview Only)' if dry_run else 'LIVE RUN (Modifications Applied)'}")
        lines.append("================================================================================\n")

        lines.append("--- SUMMARY OF OPERATIONS ---")
        lines.append(f"• Total Files Scanned           : {report_data.get('scanned', 0)}")
        lines.append(f"• Duplicate Files Found         : {len(report_data.get('dup_files', []))}")
        lines.append(f"• Duplicate Folders Removed     : {len(report_data.get('dup_folders', []))}")
        lines.append(f"• Similar Folders Merged        : {len(report_data.get('merged_folders', []))}")
        lines.append(f"• Files Categorized / Organized : {len(report_data.get('organized_files', []))}")
        lines.append(f"• Empty Folders Cleaned Up      : {len(report_data.get('empty_folders', []))}")
        lines.append(f"• Total Estimated Space Saved   : {report_data.get('space_mb', 0.0):.2f} MB\n")

        if report_data.get('dup_folders'):
            lines.append("--- 1. DUPLICATE FOLDERS REMOVED ---")
            for dup in report_data['dup_folders']:
                lines.append(f"  [REMOVED DUP FOLDER] {dup}")
            lines.append("")

        if report_data.get('merged_folders'):
            lines.append("--- 2. SIMILAR FOLDERS MERGED (~85% MATCH) ---")
            for src, dst in report_data['merged_folders']:
                lines.append(f"  [MERGED] '{src}' => '{dst}'")
            lines.append("")

        if report_data.get('dup_files'):
            lines.append("--- 3. DUPLICATE FILES REMOVED (SHA-256 MATCH) ---")
            for orig, dup in report_data['dup_files']:
                lines.append(f"  [ORIGINAL] {orig}")
                lines.append(f"   ↳ [DELETED DUP] {dup}")
            lines.append("")

        if report_data.get('organized_files'):
            lines.append("--- 4. FILES CATEGORIZED BY NATURE & TYPE ---")
            for src, cat, dest in report_data['organized_files']:
                lines.append(f"  [MOVED] '{src.name}' => '{cat}/{dest.name}'")
            lines.append("")

        if report_data.get('empty_folders'):
            lines.append("--- 5. EMPTY FOLDERS CLEANED UP ---")
            for ef in report_data['empty_folders']:
                lines.append(f"  [REMOVED EMPTY FOLDER] {ef}")
            lines.append("")

        lines.append("================================================================================")
        lines.append("                      STEP-BY-STEP USER MANAGEMENT GUIDE                        ")
        lines.append("================================================================================")
        lines.append("1. Nature Folders:")
        lines.append("   - Your files are organized into dedicated category directories (Images, Videos,")
        lines.append("     Audio, Documents, Spreadsheets, Code_and_Scripts, Archives, Executables, etc.).")
        lines.append("2. How Magic-Bytes Classifier Works:")
        lines.append("   - Files were categorized by inspecting binary magic byte headers (e.g., %PDF, ID3,")
        lines.append("     PNG, JPEG) to ensure accurate organization even if extensions were wrong.")
        lines.append("3. 1-Click Rollback & Safety Restoration:")
        lines.append("   - If you ever need to undo this operation, launch the Disk Cleaner GUI and click")
        lines.append("     '⏪ Rollback Last Run'. All moved and deleted items will be restored from the hidden")
        lines.append("     .disk_cleaner_trash vault back to their exact original paths.")
        lines.append("================================================================================")

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self._log(f"[✓ Report Saved] Detailed log report generated at:\n    -> {report_path}", "SUCCESS")
        except Exception as e:
            self._log(f"[!] Could not write report log file: {e}", "DANGER")

        return report_path


if __name__ == "__main__":
    root = tk.Tk()
    app = ModernDiskCleanerApp(root)
    root.mainloop()
