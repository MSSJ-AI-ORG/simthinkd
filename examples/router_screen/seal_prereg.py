"""Seal a preregistration before the experiment runs, and verify it afterwards.

    python seal_prereg.py seal PREREG_mine.json --freeze run.py screens.py
    python seal_prereg.py verify PREREG_mine.json

seal: records the SHA-256 of every frozen file (paths relative to the PREREG file) and the sealing time inside the
PREREG, then writes PREREG_mine.sha256 next to it. It refuses if that .sha256 already exists: a sealed PREREG is never
sealed again; write a new one (…_v2) instead. verify: exit 0 only if the PREREG still has its sealed hash and every
frozen file still has its recorded hash; prints what changed otherwise.

Line endings are normalised (CRLF -> LF) before hashing, so a Windows checkout and a Linux checkout give the same hash.
This is the procedure of experiments v2.1 and v2.2: seal after the pilot, before teacher runs and tests; report results as
measured; never re-run with changed thresholds under the same PREREG.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def seal_path(prereg):
    return Path(prereg).with_suffix('.sha256')


def seal(prereg, freeze):
    prereg = Path(prereg)
    if seal_path(prereg).exists():
        raise SystemExit(f'{seal_path(prereg).name} exists: this PREREG is already sealed (write a new one instead)')
    data = json.loads(prereg.read_text(encoding='utf8'))
    if not freeze:
        raise SystemExit('name at least one file to freeze (the code that runs the experiment)')
    frozen = {}
    for name in freeze:
        path = prereg.parent / name
        if not path.is_file():
            raise SystemExit(f'frozen file not found: {path}')
        frozen[Path(name).as_posix()] = digest(path)
    data['frozen'] = frozen
    data['sealed_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    prereg.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf8')
    value = digest(prereg)
    seal_path(prereg).write_text(f'{value}  {prereg.name}\n', encoding='utf8')
    return value


def verify(prereg):
    """List of problems (empty = sealed and unchanged)."""
    prereg = Path(prereg)
    if not seal_path(prereg).exists():
        return [f'{prereg.name} is not sealed ({seal_path(prereg).name} missing)']
    problems = []
    recorded = seal_path(prereg).read_text(encoding='utf8').split()[0]
    if digest(prereg) != recorded:
        problems.append(f'{prereg.name} changed after sealing')
    data = json.loads(prereg.read_text(encoding='utf8'))
    if not data.get('frozen'):
        problems.append('no frozen files recorded')
    for name, value in (data.get('frozen') or {}).items():
        path = prereg.parent / name
        if not path.is_file():
            problems.append(f'frozen file missing: {name}')
        elif digest(path) != value:
            problems.append(f'frozen file changed: {name}')
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description='Seal or verify a preregistration (PREREG) file.')
    ap.add_argument('cmd', choices=['seal', 'verify'])
    ap.add_argument('prereg')
    ap.add_argument('--freeze', nargs='*', default=[])
    a = ap.parse_args(argv)
    if a.cmd == 'seal':
        print(seal(a.prereg, a.freeze))
        return 0
    problems = verify(a.prereg)
    for p in problems:
        print('FAIL ' + p)
    if not problems:
        print('PASS sealed and unchanged: ' + Path(a.prereg).name)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
