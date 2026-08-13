# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: MIT

"""Add SPDX copyright headers to all project Python files.
Usage: python scripts/add_spdx_headers.py
"""
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent

MIT_DIRS = {"fitai/analysis", "tests", "scripts"}
AGPL_DIRS = {"auth", "agent", "tools", "providers", "routers", "models", "fitai/health_platforms", "fitai/knowledge", "core", "robot"}

HEADER_MIT = "# SPDX-FileCopyrightText: 2026 Chen Guojun\n# SPDX-License-Identifier: MIT\n\n"
HEADER_AGPL = "# SPDX-FileCopyrightText: 2026 Chen Guojun\n# SPDX-License-Identifier: AGPL-3.0-or-later\n\n"

def get_license_dir(file_path: str, parent: bool = False) -> str:
    """Determine license for a file based on its directory."""
    for d in MIT_DIRS:
        if f"/{d}/" in file_path or file_path.startswith(d + "/"):
            return "MIT"
    for d in AGPL_DIRS:
        if f"/{d}/" in file_path or file_path.startswith(d + "/"):
            return "AGPL"
    # Root-level files (server.py, config.py, database.py, diagnostics.py)
    if parent:
        return "AGPL"
    return "AGPL"

count = 0
for py_file in PROJ.rglob("*.py"):
    path_str = str(py_file.relative_to(PROJ)).replace("\\", "/")

    # Skip node_modules, .pytest_cache, exercises-dataset-main, etc.
    if any(skip in str(py_file) for skip in ["node_modules", ".pytest_cache", "__pycache__", "exercises-dataset-main"]):
        continue

    content = py_file.read_text(encoding="utf-8", errors="ignore")
    if content.startswith("# SPDX-FileCopyrightText:"):
        continue  # Already has header

    lic = get_license_dir(path_str)
    # Root files use AGPL
    if "/" not in path_str and lic == "AGPL":
        pass

    header = HEADER_MIT if lic == "MIT" else HEADER_AGPL
    py_file.write_text(header + content, encoding="utf-8")
    count += 1

print(f"Added SPDX headers to {count} Python files")
