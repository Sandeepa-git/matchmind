"""Zip the api/ folder for Azure Functions with forward-slash paths.

Windows PowerShell 5's Compress-Archive writes backslash paths, which Linux treats as file names,
so packages like `matchmind/` vanish on Azure. Usage: python make_api_zip.py <api_dir> <out.zip>
"""
import sys
import zipfile
from pathlib import Path

SKIP_DIRS = {".venv", "tests", ".pytest_cache", "__pycache__", "node_modules"}
SKIP_FILES = {"local.settings.json", "local.settings.json.example", "pytest.ini", "requirements-dev.txt"}

src, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
count = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        if p.is_dir() or SKIP_DIRS & set(rel.parts) or rel.name in SKIP_FILES:
            continue
        z.write(p, rel.as_posix())
        count += 1
print(f"zipped {count} files -> {out}")
