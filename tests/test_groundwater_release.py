"""Missing-month recovery retains source identity and measured means."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box
from data_ingestion import groundwater_release as release


@pytest.fixture
def crosswalk():
    return pd.DataFrame([dict(legacy_district_id='1',canonical_district_id='GJ-A',canonical_name='A',canonical_state='Gujarat'),
        dict(legacy_district_id='2',canonical_district_id='GJ-B',canonical_name='B',canonical_state='Gujarat')])


@pytest.fixture
def boundaries():
    return gpd.GeoDataFrame({'district':['A','B'],'st_nm':['Gujarat','Gujarat']},
        geometry=[box(70,20,71,21),box(71,20,72,21)],crs='EPSG:4326')


def record(**changes):
    base=dict(state_name='Gujarat',district_name='A',block='Block 1',village='Village 1',
        latitude=20.5,longitude=70.5,reported_date='10-01-2025',gwl_m_bgl=4.,source_month='2025-01',units='m_bgl')
    return {**base,**changes}


def audit(rows,crosswalk,boundaries,**kwargs):
    return release.audit_pdf_records(pd.DataFrame(rows),crosswalk,boundaries,as_of='2026-10-26',**kwargs)


def test_duplicates_contribute_once(crosswalk,boundaries):
    checked=audit([record(),record()],crosswalk,boundaries)
    assert list(checked.audit_reason)==['','duplicate_location_date_depth']
    station,monthly=release.aggregate_pdf(checked)
    assert len(station)==1 and monthly.iloc[0].reading_count==1 and monthly.iloc[0].gwl_mean==4


def test_district_rename_does_not_create_another_location(crosswalk,boundaries):
    checked=audit([record(),record(district_name='Renamed A')],crosswalk,boundaries)
    assert checked.station_key.nunique()==1
    assert checked.iloc[1].audit_reason=='duplicate_location_date_depth'


def test_conflicting_depths_are_all_quarantined(crosswalk,boundaries):
    checked=audit([record(),record(gwl_m_bgl=7)],crosswalk,boundaries)
    assert checked.audit_reason.str.contains('conflicting_location_date').all()


def test_shared_coordinate_different_labels_are_all_ambiguous(crosswalk,boundaries):
    checked=audit([record(),record(village='Other Village')],crosswalk,boundaries)
    assert checked.audit_reason.str.contains('ambiguous_colocated').all()


def test_equal_location_weights_prevent_cadence_bias(crosswalk,boundaries):
    checked=audit([record(),record(reported_date='12-01-2025',gwl_m_bgl=6),
        record(village='Village 2',longitude=70.6,gwl_m_bgl=9)],crosswalk,boundaries)
    station,monthly=release.aggregate_pdf(checked)
    assert len(station)==2 and monthly.iloc[0].gwl_mean==7
    assert monthly.iloc[0].station_count==2 and monthly.iloc[0].reading_count==3


@pytest.mark.parametrize('column,value,reason',[('gwl_m_bgl',-1,'negative_depth'),('gwl_m_bgl',301,'depth_over_300'),
    ('gwl_m_bgl',np.inf,'nonfinite_depth'),('longitude',70.0005,'near_boundary'),('longitude',71.,'unresolved_canonical'),
    ('state_name','Maharashtra','source_state_disagrees'),('village','','incomplete_source_location'),
    ('units','m_msl','unverified_depth'),('reported_date','10-02-2025','unverified_source_month'),
    ('reported_date','31-02-2025','invalid_reported_date'),('latitude',99.,'invalid_india')])
def test_unreviewed_values_quarantined(column,value,reason,crosswalk,boundaries):
    checked=audit([record(**{column:value})],crosswalk,boundaries)
    assert reason in checked.iloc[0].audit_reason


def test_boundary_margin_cannot_be_weakened(crosswalk,boundaries):
    with pytest.raises(ValueError,match='boundary margin'):
        audit([record()],crosswalk,boundaries,boundary_margin=0)


@pytest.mark.parametrize('mutation',['unknown_flag','duplicate','not_month_start','invalid_date'])
def test_bad_feature_provenance_not_treated_as_a_gap(mutation):
    frame=pd.DataFrame({'district_id':['GJ-A'],'date':['2025-01-01'],'is_observed':[True]})
    if mutation=='unknown_flag':frame['is_observed']='unknown'
    elif mutation=='duplicate':frame=pd.concat([frame,frame],ignore_index=True)
    elif mutation=='not_month_start':frame['date']='2025-01-02'
    else:frame['date']='invalid'
    with pytest.raises(ValueError,match='unknown flags'):
        release.observed_keys(frame)


def test_explicit_observation_flags_control_retention():
    frame=pd.DataFrame({'district_id':['GJ-A','GJ-B'],'date':['2025-01-01']*2,'is_observed':['True','False']})
    assert release.observed_keys(frame)=={('GJ-A',pd.Timestamp('2025-01-01'))}


def test_source_hash_change_fails_before_pdf_records_used(tmp_path):
    (tmp_path/'extraction_manifest.json').write_text('{"source_sha256":"changed"}')
    pdf=tmp_path/'source.pdf';pdf.write_bytes(b'%PDF-example')
    with pytest.raises(ValueError,match='verified source chain'):
        release.load_verified_pdf_records(tmp_path,pdf)


def test_new_metadata_paths_are_relative_and_cannot_escape_checkout(tmp_path,monkeypatch):
    monkeypatch.setattr(release,'ROOT',tmp_path)
    path=tmp_path/'data'/'source.pdf';path.parent.mkdir();path.write_bytes(b'example')
    assert release.repository_path(path)=='data/source.pdf'
    with pytest.raises(ValueError):
        release.repository_path(tmp_path.parent/'outside.pdf')
