---
description: SpecKit Implement - Code Quality & Implementation Standard
---

# SpecKit Implementation Workflow

Use this workflow to implement clean, high-performance code:

1. **Modular Code Structure**: Keep GUI separate from cleaning engines and safety vault logic.
2. **Error Safety**: Wrap file system interactions in `try/except` blocks handling `PermissionError` and `OSError`.
3. **Logging & Diagnostics**: Provide clear log messages with colored tags (`ACCENT`, `WARNING`, `SUCCESS`, `DANGER`).
