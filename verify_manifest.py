"""Check the deposited package; the manifest does not timestamp itself."""
import hashlib
from pathlib import Path

root = Path(__file__).resolve().parent
lines = (root / 'MANIFEST.sha256').read_text().splitlines()
for line in lines:
    expected, relative = line.split('  ', 1)
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise SystemExit(f'Invalid manifest path: {relative}')
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f'Hash mismatch: {relative}')
print(f'OK: {len(lines)} deposited files match SHA-256 manifest')
