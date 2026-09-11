"""Check current source compatibility and archived evidence, with or without Git."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import uuid

import numpy as np

from .archive import write_json
from .inputs import read_config
from .provenance import artifact_sha256, source_snapshot, verify_sources, git_commit, HASH_SCHEME
from .sensitivity import load_series
from .sensitivity_report import verified_runs


def test_sources():
    paths=list(Path('tests').glob('test_*.py'))+[Path('q1')/name for name in
        ('sensitivity_report.py','sensitivity_reproduce.py','sensitivity_audit.py')]
    return {p.as_posix():artifact_sha256(p) for p in sorted(paths)}


def record_tests(root):
    source=source_snapshot()
    tests=test_sources()
    scratch=Path('.scratch').resolve()
    scratch.mkdir(exist_ok=True)
    temporary=scratch/f'provenance-tests-{uuid.uuid4().hex}'
    if not temporary.is_relative_to(scratch) or temporary.exists():
        raise ValueError('Test temporary directory must be a new workspace child')
    command=[sys.executable,'-m','pytest','-q','--basetemp',str(temporary),'-p','no:cacheprovider']
    result=subprocess.run(command,capture_output=True,text=True)
    output=result.stdout+result.stderr
    root.mkdir(parents=True,exist_ok=True)
    (root/'unit_tests.txt').write_text(output,encoding='utf-8')
    match=re.search(r'(\d+) passed',output)
    passed=result.returncode==0 and match is not None and test_sources()==tests
    verify_sources(source)
    record={'passed':passed,'count':int(match[1]) if match else 0,'source_digest':source['source_digest'],
            'test_source_hashes':tests,'log_sha256':artifact_sha256(root/'unit_tests.txt'),
            'command':['python','-m','pytest','-q','--basetemp','<new-workspace-scratch-path>','-p','no:cacheprovider']}
    write_json(root/'unit_tests.json',record)
    if not passed:
        raise RuntimeError(output)


def audit(directory='results/q1_sensitivity',*,write=False,run_tests=False):
    root=Path(directory)
    if run_tests:
        record_tests(root)
    m,v,records=verified_runs(root)
    source_match=verify_sources(m)
    if len(records)!=33 or len(v['responses'])!=13:
        raise ValueError('Incomplete scenario or numerical audit coverage')
    e=read_config(root/'export_verification.json')
    if (not e['passed'] or e.get('artifact_hash_scheme')!=HASH_SCHEME
        or e['verification_sha256']!=artifact_sha256(root/'verification.json')
        or e['generator_sha256']!=artifact_sha256('q1/sensitivity_report.py')
        or not all(artifact_sha256(p)==h for p,h in e['artifact_sha256'].items())):
        raise ValueError('Stale export/report evidence; regenerate from verified sources')
    tests=read_config(root/'unit_tests.json')
    if (not tests['passed'] or tests['source_digest']!=m['source_digest']
        or tests['test_source_hashes']!=test_sources()
        or tests['log_sha256']!=artifact_sha256(root/'unit_tests.txt')):
        raise ValueError('Current sources/tests differ from tested sources; use --run-tests')
    rep=read_config(root/'reproduction.json')
    if (not rep['passed'] or rep['cache_used'] or rep['source_digest']!=m['source_digest']
        or rep['new_run_sha256']!=artifact_sha256(rep['new_run_record'])):
        raise ValueError('Missing or stale fresh-reintegration evidence')
    rr=read_config(rep['new_run_record'])
    repro_root=Path(rep['new_run_record']).parent
    if not all(artifact_sha256(repro_root/f)==h for f,h in rr['files'].items()):
        raise ValueError('Fresh-reintegration archive hash mismatch')
    sample_count=0
    for key in records:
        d=load_series(root/'runs'/key/'series.npz')
        if not np.array_equal(d['time_s'],np.arange(1801.)) or not np.allclose(d['radius_m'],np.linspace(0,.02,21),rtol=0,atol=1e-18):
            raise ValueError(f'Invalid axes in {key}')
        for f,initial in (('temperature_C',28.),('moisture',2.55)):
            u=d[f]
            if u.shape!=(1801,21) or u.dtype!=np.float64 or not np.isfinite(u).all() or not np.array_equal(u[0],np.full(21,initial)):
                raise ValueError(f'Invalid field in {key}')
            sample_count+=u.size
    record={'passed':True,'artifact_hash_scheme':HASH_SCHEME,'production_scenarios':13,'numerical_runs':33,
            'additional_fresh_reintegration':1,'formal_field_values_checked':sample_count,
            'unit_tests_passed':tests['count'],'code_commit':git_commit(),'calculation_code_commit':m['code_commit'],
            'current_source_match':source_match,'source_digest':m['source_digest'],
            'reporting_source_sha256':{p:artifact_sha256(p) for p in
                ('q1/sensitivity_report.py','q1/sensitivity_reproduce.py','q1/sensitivity_audit.py')},
            'protected_artifacts_match':True,'reproduction_passed':True,
            'endpoint_csv_readback_max_abs':e['max_endpoint_readback_difference'],
            'verification_sha256':artifact_sha256(root/'verification.json'),
            'export_verification_sha256':artifact_sha256(root/'export_verification.json')}
    if write:
        write_json(root/'delivery_audit.json',record)
    print(f"Audit passed: current commit={record['code_commit']}; source_digest={m['source_digest']}; {len(records)} runs; {tests['count']} tests.")
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default='results/q1_sensitivity')
    parser.add_argument('--write',action='store_true',help='Write a new audit; default is read-only')
    parser.add_argument('--run-tests',action='store_true',help='Run pytest and record current test/source hashes')
    args=parser.parse_args()
    audit(args.directory,write=args.write,run_tests=args.run_tests)
