"""Actually inspect an independent environment and a code-only checkout."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess


def run(checkout, python, output):
    checkout,python,output=Path(checkout).resolve(),Path(python).resolve(),Path(output).resolve()
    if output.exists():raise FileExistsError('Choose a new probe report.')
    health=subprocess.run([str(python),'-m','pip','check'],capture_output=True,text=True,timeout=120,check=False)
    if health.returncode:raise RuntimeError('Independent environment has broken package requirements.')
    code="""import sys,json,importlib.metadata as m
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from models.xgboost_model import load_feature_matrix
from models.climate_forecast_12m import load_bundle
root=Path(sys.argv[1]);failure=None
try:load_feature_matrix()
except (ValueError,FileNotFoundError) as error:failure={'type':type(error).__name__,'message':str(error)}
model,card=load_bundle(expected_generation='physical-v3-causal-monthly-a3f9468a2569')
names=['numpy','pandas','scipy','xgboost','scikit-learn','Flask','netCDF4','geopandas']
missing=[name for name in ['data/raw/cgwb_combined.csv','data/raw/india_districts.geojson','data/processed/features_matrix.csv','data/processed/feature_manifest.json','.env'] if not(root/name).exists()]
print(json.dumps({'python':sys.version.split()[0],'prefix':sys.prefix,'packages':{n:m.version(n) for n in names},'code_only_feature_load':failure,'tracked_model_verified_sha256':card['model_sha256'],'missing_runtime_assets':missing}))
"""
    result=subprocess.run([str(python),'-I','-B','-c',code,str(checkout)],cwd=checkout,
        capture_output=True,text=True,timeout=120,check=False)
    if result.returncode:raise RuntimeError('Independent checkout probe failed; inspect its local diagnostic output.')
    evidence=json.loads(result.stdout.strip().splitlines()[-1])
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip()
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'checkout_commit':head,
        'independent_environment':True,'shared_site_packages':False,'pip_check':'passed',
        'probe':evidence,'code_only_clone_reproduces_forecasts':False,
        'source_asset_status':'Code-only feature loading was actually attempted. Exact ignored baseline assets and a credentialed local test database require separate acquisition/restoration; metadata access alone is not asset availability.',
        'supplied_asset_replay':'not_yet_attempted','working_service_modified':False,'database_writes':False}
    if not evidence['code_only_feature_load'] or not evidence['missing_runtime_assets']:
        raise ValueError('Initial probe must run before provisioned runtime data.')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkout',type=Path,required=True);p.add_argument('--python',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.checkout,a.python,a.output)
