"""Reuse unchanged pre-origin radii only after exact calibration-era input proof."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd

from models import climate_forecast_12m as climate
from models.tiered_forecast import VERSION
from models.xgboost_model import load_feature_matrix, sha256_file, _write_json


def prove_calibration_prefix(parent, candidate, cutoff):
    columns=sorted(c for c in parent if c!='feature_generation')
    if set(columns)!=set(c for c in candidate if c!='feature_generation'):
        raise ValueError('Calibration feature schema differs.')
    a=parent.loc[parent.date.le(pd.Timestamp(cutoff)),columns].sort_values(['district_id','date']).reset_index(drop=True)
    b=candidate.loc[candidate.date.le(pd.Timestamp(cutoff)),columns].sort_values(['district_id','date']).reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(a,b,check_dtype=False,check_exact=True)
    except AssertionError as error:
        raise ValueError('Calibration-era inputs/labels changed; historical radii cannot be rebound.') from error
    return len(a)


def prepare(parent_directory,candidate_directory,calibration_path,output):
    output=Path(output)
    if output.exists():raise FileExistsError('Choose a new calibration output; existing evidence is immutable.')
    parent=load_feature_matrix(parent_directory);candidate=load_feature_matrix(candidate_directory)
    card=json.loads(Path(calibration_path).read_text(encoding='utf-8'))
    if (card['feature_generation_id']!=parent.attrs['feature_generation_id']
            or card['feature_data_sha256']!=parent.attrs['feature_manifest']['feature_csv_sha256']):
        raise ValueError('Parent calibration does not match the verified parent features.')
    bundle=climate.load_bundle(Path(candidate_directory)/'frozen_bundle/checkpoint.json',expected_generation=candidate.attrs['feature_generation_id'])
    if bundle[1]['model_sha256']!=card['xgboost_sha256']:
        raise ValueError('Changed model weights require independent calibration.')
    count=prove_calibration_prefix(parent,candidate,card['max_calibration_target'])
    updated=deepcopy(card)
    updated.update(pipeline_version=VERSION,feature_generation_id=candidate.attrs['feature_generation_id'],
        feature_data_sha256=candidate.attrs['feature_manifest']['feature_csv_sha256'],
        parent_calibration_sha256=sha256_file(calibration_path),
        compatibility_proof={'parent_feature_generation':parent.attrs['feature_generation_id'],
            'compared_rows':count,'through_date':card['max_calibration_target'],
            'all_input_and_label_values_identical':True,'radii_changed':False,
            'final_labels_used':False,
            'reason':'Additional measurements are after all calibration inputs and targets. Point weights and causal feature definitions remain unchanged.'})
    _write_json(output,updated)
    print(json.dumps(updated['compatibility_proof'],indent=2))
    return updated


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent-directory',type=Path,required=True);p.add_argument('--candidate-directory',type=Path,required=True)
    p.add_argument('--calibration',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.parent_directory,a.candidate_directory,a.calibration,a.output)
