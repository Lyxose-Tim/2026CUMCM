"""Portable source identity; Git metadata is optional, changed code is not."""
import hashlib
import json
from pathlib import Path
import subprocess

from .inputs import sha256


HASH_SCHEME='sha256-text-lf-v1'
TEXT_SUFFIXES={'.py','.json','.csv','.md','.txt'}
NUMERICAL_FILES=tuple(f'q1/{name}.py' for name in (
    '__init__','archive','inputs','fvm','solver','validation','reference',
    'sensitivity','sensitivity_metrics','provenance'))+(
    'configs/q1.json','configs/q1_sensitivity.json','requirements.lock.txt')


def artifact_sha256(path):
    """Normalize CRLF only for declared text types; binary bytes remain exact."""
    path=Path(path)
    if path.suffix.lower() in TEXT_SUFFIXES:
        return hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    return sha256(path)


def source_digest(hashes):
    return hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def git_commit(directory='.'):
    """Do not require Git or accidentally identify the ZIP's parent repository."""
    directory=Path(directory).resolve()
    try:
        top=subprocess.run(['git','-C',str(directory),'rev-parse','--show-toplevel'],
                           capture_output=True,text=True,timeout=5,check=False)
        if top.returncode or Path(top.stdout.strip()).resolve()!=directory:
            return None
        result=subprocess.run(['git','-C',str(directory),'rev-parse','HEAD'],
                              capture_output=True,text=True,timeout=5,check=False)
        return result.stdout.strip() if result.returncode==0 else None
    except (OSError,subprocess.SubprocessError):
        return None


def source_snapshot(directory='.'):
    root=Path(directory)
    hashes={p:artifact_sha256(root/p) for p in NUMERICAL_FILES}
    return {'source_hash_scheme':HASH_SCHEME,'source_hashes':hashes,
            'source_raw_hashes':{p:sha256(root/p) for p in NUMERICAL_FILES},
            'source_digest':source_digest(hashes),'code_commit':git_commit(root)}


def verify_sources(record,directory='.'):
    if record.get('source_hash_scheme')!=HASH_SCHEME:
        raise ValueError('Unverified legacy source provenance; rerun with current source tracking')
    if set(record.get('source_hashes',{}))!=set(NUMERICAL_FILES):
        raise ValueError('Numerical source scope is incomplete or changed')
    current=source_snapshot(directory)
    changed=[p for p in NUMERICAL_FILES if current['source_hashes'][p]!=record['source_hashes'][p]]
    if changed:
        raise ValueError('Current numerical source mismatch: '+', '.join(changed))
    if record.get('source_digest')!=current['source_digest']:
        raise ValueError('Recorded source digest does not match its source manifest')
    return {'matches':True,'source_digest':current['source_digest'],'current_code_commit':current['code_commit'],
            'raw_byte_differences':[p for p in NUMERICAL_FILES if current['source_raw_hashes'][p]!=record.get('source_raw_hashes',{}).get(p)]}
