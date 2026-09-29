---
description: SpecKit Constitution - Project Governance, Safety Protocols, and Quality Standards
---

# SpecKit Constitution

This document defines the mandatory governing rules for the Disk Cleaner & Smart File Organizer project:

1. **Safety First**: All destructive file operations (deletions, moves) MUST be intercepted by the `SafetyVault` unless explicitly disabled by the user.
2. **Developer Project Safeguard**: Code project directories (Laravel `artisan`, Node `package.json`/`node_modules`, Rust `Cargo.toml`, Go `go.mod`, Python `requirements.txt`, Git `.git`, C/C++ `Makefile`) MUST BE PROTECTED. Never merge similar developer projects or re-organize internal project source code.
3. **1-Click Rollback Integrity**: Every transaction must record original file paths and backup locations to JSON history for instant restoration.
4. **Task Resume Checkpoints**: Operations must save progress to `checkpoint.json` on cancellation/pause, allowing users to resume stopped tasks without repeating completed work.
5. **Real-Time Live Directory Sync**: File scanning and processing must dynamically validate `os.stat` mtime and file existence to seamlessly incorporate incoming file updates while running.
6. **High-Power Multi-Threaded Performance**: File hashing must run in parallel across CPU cores using `ThreadPoolExecutor(max_workers=os.cpu_count())` without blocking the main GUI thread.
7. **Real-Time Progress & Cancellation**: Progress must be reported live (0% - 100%) and operations MUST support 1-Click user cancellation (`🛑 Stop`).
8. **Content-Aware Intelligence**: File organization must prioritize binary magic bytes over plain file extensions.
9. **Non-Blocking GUI**: All heavy operations must run in background daemon threads with rate-limited UI updates to prevent Tkinter interface freezes.
