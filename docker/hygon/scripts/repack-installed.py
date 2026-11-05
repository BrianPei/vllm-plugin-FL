"""Reconstitute a wheel from a pinned image; verify original RECORD hashes.

This does not claim byte identity with the original vendor wheel.
"""
import base64
import csv
import hashlib
import importlib.metadata as m
import io
import json
from pathlib import Path
import sys
import zipfile

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
for name in sys.argv[2:]:
    d = m.distribution(name)
    files = list(d.files or [])
    metadata = next(p for p in files if p.name == 'METADATA' and p.parent.name.endswith('.dist-info'))
    info = metadata.parent.name
    stem = info.removesuffix('.dist-info')
    wheel = d.read_text('WHEEL')
    tags = [s[5:] for s in wheel.splitlines() if s.startswith('Tag: ')]
    assert tags and len(tags) == 1, tags
    dest = out / (stem + '-' + tags[0] + '.whl')
    rows = []; verified = 0; mismatches = []; shared_verified = []
    alternate = {}
    if name == 'triton':
        tree = m.distribution('flagtree')
        alternate = {Path(tree.locate_file(f)).resolve(): f for f in tree.files or [] if f.hash}
    with zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for item in files:
            if item.name == 'RECORD' or str(item).endswith(('.pyc', '.pyo')): continue
            source = Path(d.locate_file(item))
            if not source.is_file(): raise RuntimeError(f'Missing {source}')
            target = str(item)
            if '..' in item.parts:
                assert source.parent.name == 'bin', source
                target = stem + '.data/scripts/' + source.name
            data = source.read_bytes()
            digest = hashlib.sha256(data).digest()
            if item.hash:
                actual = base64.urlsafe_b64encode(hashlib.new(item.hash.mode, data).digest()).rstrip(b'=').decode()
                if actual != item.hash.value:
                    other = alternate.get(source.resolve())
                    if other and base64.urlsafe_b64encode(hashlib.new(other.hash.mode, data).digest()).rstrip(b'=').decode() == other.hash.value:
                        shared_verified.append(str(item))
                    elif name == 'triton' and str(item) == 'triton/backends/__init__.py' and hashlib.sha256(data).hexdigest() == 'bdc98761bdca3a4c16b52c6e10169af753c598015e449d58c26ed70431af4407':
                        shared_verified.append('pinned image backend-discovery patch: ' + str(item))
                    else: mismatches.append(str(item))
                else: verified += 1
            z.writestr(target, data)
            rows.append((target, 'sha256=' + base64.urlsafe_b64encode(digest).rstrip(b'=').decode(), len(data)))
        rows.append((info + '/RECORD', '', ''))
        buf = io.StringIO(); csv.writer(buf, lineterminator='\n').writerows(rows)
        z.writestr(info + '/RECORD', buf.getvalue())
    report = {'name': name, 'version': d.version, 'verified_original_files': verified, 'original_record_mismatches': mismatches, 'verified_against_flagtree_record': shared_verified, 'wheel': dest.name, 'sha256': hashlib.file_digest(open(dest, 'rb'), 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(dest.read_bytes()).hexdigest()}
    (out / (stem + '.provenance.json')).write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    if mismatches: raise RuntimeError('Original RECORD mismatches; do not install this artifact')
