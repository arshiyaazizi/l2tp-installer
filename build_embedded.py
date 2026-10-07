#!/usr/bin/env python3
"""جاسازی پوشه files/ داخل install.sh (حالت one-liner)"""
import base64
import io
import pathlib
import tarfile

ROOT = pathlib.Path("/root/l2tp-repo")
FILES_DIR = ROOT / "files"
TARGET = ROOT / "install.sh"
PLACEHOLDER = "__FILES_PAYLOAD__"

# --- ساخت tar از files/ ---
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for p in sorted(FILES_DIR.rglob("*")):
        if p.is_file() or p.is_symlink():
            tar.add(p, arcname="files/" + str(p.relative_to(FILES_DIR)))
payload = base64.b64encode(buf.getvalue()).decode("ascii")
print(f"files/ -> tar.gz {len(buf.getvalue())} bytes -> base64 {len(payload)} chars")

# --- جایگزینی placeholder ---
text = TARGET.read_text(encoding="utf-8")
if PLACEHOLDER not in text:
    raise SystemExit("placeholder پیدا نشد (قبلاً جایگزین شده؟)")
text = text.replace(PLACEHOLDER, payload, 1)
TARGET.write_text(text, encoding="utf-8")
print(f"install.sh -> {TARGET.stat().st_size} bytes")

# --- اعتبارسنجی: آیا payload درسته؟ ---
import subprocess, tempfile, shutil
tmp = pathlib.Path(tempfile.mkdtemp())
proc = subprocess.run(["bash", "-c", f"printf '%s' {payload} | base64 -d | tar -xz -C {tmp}"],
                      capture_output=True)
if proc.returncode != 0:
    raise SystemExit(f"decode failed: {proc.stderr[:200]}")
ok = 0
for p in FILES_DIR.rglob("*"):
    if p.is_file():
        rel = "files/" + str(p.relative_to(FILES_DIR))
        if (tmp / rel).exists():
            ok += 1
        else:
            raise SystemExit(f"missing after decode: {rel}")
print(f"✓ payload verified: {ok} files decode correctly")
shutil.rmtree(tmp, ignore_errors=True)
