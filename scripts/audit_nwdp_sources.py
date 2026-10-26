"""Reproduce comparable station-day source coverage and rejected telemetry audit."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_ingestion.nwdp_manual import _fingerprint,sha256,parse_telemetry_csv
import argparse

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw/official_enrichment/nwdp_20261026"))
    parser.add_argument("--candidate-dir", type=Path, default=Path("reports/candidates/groundwater_updates/enrichment_20261026/nwdp_manual_v1"))
    parser.add_argument("--existing-raw", type=Path, default=Path("data/raw/cgwb_combined.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/data_enrichment"))
    args=parser.parse_args(argv)
    p=Path(args.source_dir)
    c=Path(args.candidate_dir)
    o=Path(args.output_dir);o.mkdir(parents=True,exist_ok=True)
    acquisition=json.loads((p/'manual_acquisition.json').read_text())
    manifest=json.loads((c/'manifest.json').read_text())
    raw=pd.read_csv(args.existing_raw,usecols=['state_name','station_name','latitude','longitude','date','currentlevel'],keep_default_na=False)
    for col in ['latitude','longitude','currentlevel']:raw[col]=pd.to_numeric(raw[col],errors='coerce')
    if sha256(args.existing_raw) != manifest["existing_raw_sha256"]:
        raise ValueError("Original raw input differs from audited candidate baseline")
    for filename in ["accepted_station_records.csv", "station_audit.csv"]:
        if sha256(c/filename) != manifest["output_sha256"][filename]:
            raise ValueError("Candidate station provenance checksum changed")
    raw['date']=pd.to_datetime(raw.date,errors='coerce').dt.normalize()
    raw['station_key']=[_fingerprint(s,n,a,b) for s,n,a,b in zip(raw.state_name,raw.station_name,raw.latitude,raw.longitude)]
    valid=np.isfinite(raw.currentlevel)&raw.currentlevel.ge(0)&np.isfinite(raw.latitude)&raw.latitude.between(6,38)&np.isfinite(raw.longitude)&raw.longitude.between(68,98)&raw.date.notna()
    base=raw.loc[valid,['station_key','date','currentlevel']].rename(columns={'currentlevel':'value'})
    new=pd.read_csv(c/'accepted_station_records.csv',usecols=['station_key','observation_date','gwl_m_bgl'])
    new=new.rename(columns={'observation_date':'date','gwl_m_bgl':'value'});new['date']=pd.to_datetime(new.date).dt.normalize()
    union=pd.concat([base,new],ignore_index=True)
    def counts(f):return {'station_fingerprints':int(f.station_key.nunique()),'distinct_station_days':len(f[['station_key','date']].drop_duplicates()),'distinct_station_day_depth_records':len(f.drop_duplicates()),'valid_reading_rows':len(f),'first_observation_date':str(f.date.min().date()),'last_observation_date':str(f.date.max().date())}
    resources=[]
    for x in manifest['sources']:
        resources.append({k:x.get(k) for k in ['id','name','url','sha256','size_bytes','metadata_last_modified','license_id','license_title','license_url','row_count','first_observation_date','last_observation_date']})
    report={'old_raw_sha256':sha256(args.existing_raw),'old_raw_input_rows':len(raw),'raw_validity_for_comparison':'Finite nonnegative depth, valid India coordinates and actual date only; original legacy spatial assignment is not certified by this comparison. No old raw row is modified. Station identity normalized exact name/state + coordinates rounded5decimals; old source has daily resolution only.','old_raw_nonfinite_or_negative_depth_rows':int((~np.isfinite(raw.currentlevel)|raw.currentlevel.lt(0)).sum()),'old_raw_depth_over_300m_review_rows':int(raw.currentlevel.gt(300).sum()),'before':counts(base),'after_manual_accepted_union':counts(union),'new_accepted_source_timestamps':manifest['accepted_station_timestamps'],'accepted_rows_collapse_to_distinct_station_days':len(new[['station_key','date']].drop_duplicates()),'new_distinct_station_fingerprints':int(len(set(new.station_key)-set(base.station_key))),'new_distinct_station_days':len(union[['station_key','date']].drop_duplicates())-len(base[['station_key','date']].drop_duplicates()),'new_distinct_station_day_depth_records':len(union.drop_duplicates())-len(base.drop_duplicates()),'district_month_candidate_summary':{k:manifest[k] for k in ['source_rows','accepted_source_rows','rejected_source_rows','rejection_reasons','existing_raw_comparison','canonical_districts','district_months','new_district_months_vs_features','newly_locally_observed_districts','first_observation_date','last_observation_date']},'manual_resources':resources,'manual_metadata_sha256':acquisition['metadata_sha256'],'manual_dataset_url':acquisition['dataset_url'],'manual_status':{'discovered':True,'accessible':True,'downloaded':True,'parsed':True,'integrated':'candidate_feature_generation_only','validated':'parser/audit tests; modeling evaluation reported separately'},'all_manual_2026_2030_resources':'31 downloaded and schema verified: header-only, zero observations. Not a future measured series.','raw_files_committed':False,'production_database_modified':False,'caveats':['An exact location fingerprint is not a certified globally unique physical well identifier. Raw legacy timestamps have day precision, so only station-day comparisons are commensurate.','Finite/positive depth screening alone does not independently validate old raw measurement datum or legacy mapping.','New NWDP records are conservative audited candidates; existing genuine district-month aggregates retained rather than reaveraged.','Other(Open) license metadata has no specific license URL. Keep raw files local and attribute CGWB/NWIC.']}
    (o/'groundwater_sources.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print('COVERAGE',json.dumps({k:report[k] for k in ['before','after_manual_accepted_union','new_distinct_station_fingerprints','new_distinct_station_days','new_distinct_station_day_depth_records']}),flush=True)
    tmeta=json.loads((p/'telemetry_acquisition.json').read_text())
    frames=[];tresources=[]
    for x in tmeta['resources']:
        f=parse_telemetry_csv(x['path'],source_url=x['url'],resource_id=x['id'],expected_sha256=x['sha256'])
        f['gwl_m_bgl']=pd.to_numeric(f.gwl_m_bgl,errors='coerce')
        f['station_key']=[_fingerprint(s,n,float(a),float(b)) for s,n,a,b in zip(f.state_name,f.station_name,f.latitude,f.longitude)]
        frames.append(f)
        tresources.append({**{k:x.get(k) for k in ['id','name','url','sha256','size_bytes','license_id','license_title','metadata_last_modified']},'rows':len(f),'first_observation_date':str(f.observation_date.min().date()),'last_observation_date':str(f.observation_date.max().date())})
    t=pd.concat(frames,ignore_index=True)
    daily=t.groupby(['station_key','observation_date'],as_index=False).gwl_m_bgl.mean()
    man=pd.read_csv(c/'station_audit.csv',usecols=['station_key','observation_date','gwl_m_bgl'])
    man['observation_date']=pd.to_datetime(man.observation_date)
    manual_day=man.groupby(['station_key','observation_date'],as_index=False).gwl_m_bgl.mean()
    overlap=daily.merge(manual_day,on=['station_key','observation_date'],suffixes=('_telemetry','_manual'))
    station_overlap=set(t.station_key)&set(man.station_key)
    cadence=t.sort_values(['station_key','observation_timestamp']).groupby('station_key').observation_timestamp.diff().dt.total_seconds()/3600
    tele={'dataset_url':tmeta['dataset_url'],'metadata_sha256':tmeta['metadata_sha256'],'resources':tresources,'source_rows':len(t),'unique_station_fingerprints':int(t.station_key.nunique()),'distinct_station_timestamps':len(t[['station_key','observation_timestamp']].drop_duplicates()),'duplicate_station_timestamp_rows':int(t.duplicated(['station_key','observation_timestamp']).sum()),'valid_numeric_rows':int(np.isfinite(t.gwl_m_bgl).sum()),'negative_numeric_rows':int(t.gwl_m_bgl.lt(0).sum()),'zero_numeric_rows':int(t.gwl_m_bgl.eq(0).sum()),'positive_numeric_rows':int(t.gwl_m_bgl.gt(0).sum()),'value_min_provider_metres':float(t.gwl_m_bgl.min()),'value_max_provider_metres':float(t.gwl_m_bgl.max()),'first_observation_date':str(t.observation_date.min().date()),'last_observation_date':str(t.observation_date.max().date()),'actual_cadence_hour_counts':{str(k):int(v) for k,v in cadence.value_counts().head(8).items()},'manual_exact_station_fingerprint_overlap':len(station_overlap),'manual_same_station_day_pairs':len(overlap),'manual_telemetry_signed_difference_mae_m':float((overlap.gwl_m_bgl_telemetry-overlap.gwl_m_bgl_manual).abs().mean()) if len(overlap) else None,'status':{'discovered':True,'accessible':True,'downloaded':True,'parsed':True,'integrated':False,'validated':False},'decision':'Retain as audited source candidate only; do not reverse signs or pool with quarterly manual targets.','blockers':['Provider telemetry values are predominantly negative while the deployed target is positive depth below ground level. Dataset title and general description do not certify a per-well sign convention or reference datum.','No independently certified cross-product well identifiers/aquifer/construction continuity. Exact name+coordinate overlap is reported but cannot establish equivalence.','Six-hourly readings require station-balanced temporal aggregation and overlap validation before modeling; no manual/telemetry pooling performed.'],'raw_files_committed':False}
    (o/'telemetry_review.json').write_text(json.dumps(tele,indent=2,allow_nan=False)+'\n')
    print('TELEMETRY',json.dumps({k:tele[k] for k in ['source_rows','unique_station_fingerprints','negative_numeric_rows','zero_numeric_rows','positive_numeric_rows','actual_cadence_hour_counts','manual_exact_station_fingerprint_overlap','manual_same_station_day_pairs','manual_telemetry_signed_difference_mae_m']}),flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
