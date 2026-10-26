"""Bounded exact-record boundary subsets never revise source coordinates."""
import io
import struct
from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import box

from data_ingestion import release_boundaries as boundary


def source(tmp_path):
    path=tmp_path/'source.shp'
    frame=gpd.GeoDataFrame({'STATE_UT':['STATE']*3,'DIST_LGD':['1','2','3'],
        'DISTRICT':['First','Middle','Last']},geometry=[box(0,0,1,1),box(2,2,3,3),box(4,4,5,5)],crs=4326)
    frame.to_file(path,engine='pyogrio')
    return path


def test_subset_preserves_exact_selected_record_content_attributes_and_coordinates(tmp_path):
    original=source(tmp_path)
    old_shp=original.read_bytes();old_shx=original.with_suffix('.shx').read_bytes();old_dbf=original.with_suffix('.dbf').read_bytes()
    shp,shx,dbf,evidence=boundary.subset_shape_stream(io.BytesIO(old_shp),old_shx,old_dbf,[0,2])
    new=tmp_path/'subset.shp';new.write_bytes(shp);new.with_suffix('.shx').write_bytes(shx);new.with_suffix('.dbf').write_bytes(dbf)
    new.with_suffix('.prj').write_bytes(original.with_suffix('.prj').read_bytes())
    old_frame=gpd.read_file(original);new_frame=gpd.read_file(new)
    assert new_frame.DISTRICT.to_list()==['First','Last']
    assert new_frame.geometry.iloc[0].equals_exact(old_frame.geometry.iloc[0],0)
    assert new_frame.geometry.iloc[1].equals_exact(old_frame.geometry.iloc[2],0)
    for part,index in zip(evidence,[0,2]):
        offset,length=struct.unpack('>II',old_shx[100+8*index:108+8*index])
        assert part['raw_record_content_sha256']==__import__('hashlib').sha256(old_shp[2*offset+8:2*offset+8+2*length]).hexdigest()
    assert original.read_bytes()==old_shp
    assert len(shp)<len(old_shp)
    assert struct.unpack('>I',shp[24:28])[0]*2==len(shp)
    assert struct.unpack('>I',shx[24:28])[0]*2==len(shx)


@pytest.mark.parametrize('indices',[[],[0,0],[-1],[3]])
def test_invalid_or_duplicate_source_indices_fail(tmp_path,indices):
    original=source(tmp_path)
    with pytest.raises(ValueError,match='indices'):
        boundary.subset_shape_stream(io.BytesIO(original.read_bytes()),original.with_suffix('.shx').read_bytes(),original.with_suffix('.dbf').read_bytes(),indices)


@pytest.mark.parametrize('problem',['truncated','index_size','bad_offset','unknown_shape'])
def test_corrupt_shapes_fail_closed(tmp_path,problem):
    original=source(tmp_path)
    shp=original.read_bytes();shx=bytearray(original.with_suffix('.shx').read_bytes());dbf=original.with_suffix('.dbf').read_bytes()
    if problem=='truncated':shp=shp[:110]
    elif problem=='index_size':shx=shx[:-8]
    elif problem=='bad_offset':shx[100:104]=struct.pack('>I',999999)
    else:
        value=bytearray(shp);value[108:112]=struct.pack('<I',3);shp=bytes(value)
    with pytest.raises(ValueError):boundary.subset_shape_stream(io.BytesIO(shp),bytes(shx),dbf,[0])


def test_deleted_source_records_do_not_silently_shift_identity(tmp_path):
    original=source(tmp_path)
    data=bytearray(original.with_suffix('.dbf').read_bytes());header=struct.unpack('<H',data[8:10])[0];data[header]=ord('*')
    with pytest.raises(ValueError,match='Deleted'):
        boundary.dbf_records(data)


class Response:
    def __init__(self,payload,status,headers):self.stream=io.BytesIO(payload);self.status=status;self.headers=headers
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,size):return self.stream.read(size)


def test_verified_partial_download_resumes_without_repeating_prefix(tmp_path,monkeypatch):
    monkeypatch.setattr(boundary,'ROOT',tmp_path)
    target=tmp_path/'data/raw/official_release/test/resource.rar';target.parent.mkdir(parents=True)
    target.with_suffix('.rar.partial').write_bytes(b'prefix')
    calls=[]
    def opener(request,timeout):
        calls.append(request)
        assert request.get_header('Range')=='bytes=6-'
        return Response(b'suffix',206,{'Last-Modified':'known','Content-Range':'bytes 6-11/12'})
    expected=__import__('hashlib').sha256(b'prefixsuffix').hexdigest()
    result=boundary.acquire_resource('https://surveyofindia.gov.in/example',target,
        expected_size=12,expected_sha256=expected,last_modified='known',opener=opener)
    assert target.read_bytes()==b'prefixsuffix' and len(calls)==1
    assert result['sha256']==expected


def test_server_ignoring_range_cannot_corrupt_partial_source(tmp_path,monkeypatch):
    monkeypatch.setattr(boundary,'ROOT',tmp_path)
    target=tmp_path/'data/raw/official_release/test/resource.rar';target.parent.mkdir(parents=True)
    partial=target.with_suffix('.rar.partial');partial.write_bytes(b'prefix')
    def opener(request,timeout):return Response(b'wrong entire resource',200,{'Last-Modified':'known'})
    with pytest.raises(ValueError,match='Content-Range'):
        boundary.acquire_resource('https://surveyofindia.gov.in/example',target,
            expected_size=12,expected_sha256='0'*64,last_modified='known',opener=opener)
    assert partial.read_bytes()==b'prefix' and not target.exists()


@pytest.mark.parametrize('url',['http://surveyofindia.gov.in/source','https://example.org/source','https://surveyofindia.gov.in/source?key=placeholder'])
def test_nonofficial_or_query_urls_are_rejected_before_network(tmp_path,monkeypatch,url):
    monkeypatch.setattr(boundary,'ROOT',tmp_path)
    def forbidden(*args,**kwargs):pytest.fail('must not contact unverified source')
    with pytest.raises(ValueError,match='official'):
        boundary.acquire_resource(url,tmp_path/'data/raw/official_release/source',expected_size=1,
            expected_sha256='0'*64,opener=forbidden)
