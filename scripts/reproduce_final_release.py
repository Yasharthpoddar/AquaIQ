"""Replay supplied verified assets in the independently installed clean checkout.

This is explicitly a supplied-asset test, not proof that ignored baseline data
can be acquired from a code-only public clone. The working service is untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from models.xgboost_model import sha256_file

ROOT=Path(__file__).resolve().parents[1]
NEW_SOURCE=(
    'data_ingestion/groundwater_release.py','data_ingestion/release_weather.py',
    'models/interval_evidence.py','models/artifacts/interval_reliability.json',
    'scripts/audit_interval_reliability.py','scripts/prepare_final_calibration.py',
    'scripts/evaluate_final_release.py','scripts/clean_release_probe.py',
)


def run(checkout,python,candidates,expected_features,calibration,output,schema):
    checkout,python,candidates,expected_features,calibration,output=map(lambda p:Path(p).resolve(),(checkout,python,candidates,expected_features,calibration,output))
    if not checkout.is_relative_to(ROOT/'scratch') or not(checkout/'.git').is_dir():
        raise ValueError('Replay requires this task\'s separate scratch Git checkout.')
    if output.exists():raise FileExistsError('Choose a new replay report.')
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    tops={'api','models','data_ingestion','preprocessing','db','scripts','dashboard'}
    names={name for name in tracked if name and (Path(name).parts[0] in tops or name in {'config.yaml','requirements.txt','setup.ps1','setup.sh'})}
    names.update(name for name in NEW_SOURCE if (ROOT/name).is_file())
    source_hashes={}
    for name in sorted(names):
        source,target=ROOT/name,checkout/name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        if sha256_file(source)!=sha256_file(target):raise ValueError('Clean source patch copy differs.')
        source_hashes[name]=sha256_file(source)
    # The source patch is public code/config only. The private credential file
    # remains ignored and its values/hash are deliberately absent from reports.
    if (ROOT/'.env').exists():shutil.copyfile(ROOT/'.env',checkout/'.env')
    asset_names=('data/raw/india_districts.geojson','data/processed/features_matrix.csv','data/processed/feature_manifest.json')
    supplied={}
    for name in asset_names:
        source,target=ROOT/name,checkout/name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        supplied[name]=sha256_file(target)
        if supplied[name]!=sha256_file(source):raise ValueError('Supplied baseline bytes differ.')
    snapshot=checkout/'data/processed/enrichment/clean_final_replay'
    cal_output=checkout/'scratch/final_replay_calibration.json'
    exports=checkout/'scratch/final_replay_outputs'
    parameters={'checkout':str(checkout),'assets':str(ROOT),'candidates':str(candidates),'snapshot':str(snapshot),
        'parent':str(ROOT/'data/processed/enrichment/nwdp_manual_20261026_v1'),
        'parent_calibration':str(ROOT/'reports/data_enrichment/final_evaluation/calibration.json'),
        'cal_output':str(cal_output),'exports':str(exports),'schema':schema}
    code="""import sys,os,json
from pathlib import Path
p=json.loads(sys.argv[1]);sys.path.insert(0,p['checkout']);os.chdir(p['assets'])
from data_ingestion.nwdp_manual import acquire_recent
from preprocessing.official_enrichment import build_snapshot
from scripts.prepare_final_calibration import prepare
from db.init_db import init_db
from scripts.precompute_forecasts import main
a=acquire_recent(Path(p['assets'])/'data/raw/official_enrichment/nwdp_20261026')
assert all(s.get('downloaded') for s in a['resources'])
b=build_snapshot(p['candidates'],p['snapshot'],as_of='2026-10-26')
prepare(p['parent'],p['snapshot'],p['parent_calibration'],p['cal_output'])
init_db(p['schema'])
result=main(['--as-of','2026-10-26','--feature-directory',p['snapshot'],
 '--checkpoint',str(Path(p['snapshot'])/'frozen_bundle/checkpoint.json'),
 '--calibration-path',p['cal_output'],'--test-schema',p['schema'],
 '--export-dir',p['exports'],'--output',str(Path(p['checkout'])/'scratch/reproduction_generation.json')])
print(json.dumps({'reproduction_complete':True,'build':b,'generation':result}))
"""
    executed=subprocess.run([str(python),'-I','-B','-c',code,json.dumps(parameters)],cwd=ROOT,
        capture_output=True,text=True,timeout=1800,check=False)
    log=checkout/'scratch/final_replay.log';log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text(executed.stdout+'\n'+executed.stderr,encoding='utf-8')
    if executed.returncode:raise RuntimeError('Supplied-asset clean replay failed; inspect the ignored checkout log.')
    result=json.loads(executed.stdout.strip().splitlines()[-1])
    expected=json.loads((expected_features/'feature_manifest.json').read_text(encoding='utf-8'))
    from models.forecast_storage import compute_input_identity
    identity=compute_input_identity('2026-10-26',feature_directory=expected_features,
        checkpoint=expected_features/'frozen_bundle/checkpoint.json',calibration_path=calibration)
    matches={'feature_generation':result['build']['generation_id']==expected['generation_id'],
        'feature_csv':result['build']['feature_csv_sha256']==expected['feature_csv_sha256'],
        'calibration_values':json.loads(cal_output.read_text(encoding='utf-8'))==json.loads(calibration.read_text(encoding='utf-8')),
        'generation_id':result['generation']['generation_id']==identity['generation_id'],
        'all_districts':result['generation']['districts_forecast']==725,
        'all_horizons':result['generation']['validation']['horizons']==8700}
    if not all(matches.values()):raise ValueError('Clean replay differs from expected identities/coverage: '+json.dumps(matches))
    source_patch_sha=hashlib.sha256(json.dumps(source_hashes,sort_keys=True).encode()).hexdigest()
    report={'test':'independent_environment_supplied_asset_replay','matches':matches,
        'source_patch_sha256':source_patch_sha,'copied_public_source_files':len(source_hashes),
        'supplied_baseline_hashes':supplied,'credential_values_or_hashes_recorded':False,
        'acquisition_command':'cached source acquisition/checksum validation succeeded; bodies were not redownloaded',
        'generation':result['generation'],'build':result['build'],'isolated_schema':schema,
        'working_service_modified':False,'public_source_tables_modified':False,
        'code_only_fresh_clone_claim':False,
        'limits':['Ignored raw/baseline data and local credentials were supplied; this is not independent acquisition of the old baseline.',
            'A public current-source catalog is not an exact download recipe for the original combined baseline hash.',
            'The source patch was applied to a clean checkout before commit; its complete public source hash is recorded.']}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('checkout','python','candidates','expected-features','calibration','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--schema',required=True)
    a=p.parse_args();run(a.checkout,a.python,a.candidates,a.expected_features,a.calibration,a.output,a.schema)
