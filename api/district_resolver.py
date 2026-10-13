"""Resolve identity from the canonical master and audited crosswalk, never data availability."""
from db.connection import get_connection, read_frame

def resolve_district_id(district_id):
    connection=get_connection()
    try:
        direct=read_frame('SELECT district_id FROM districts WHERE district_id=%s',connection,(district_id,))
        if len(direct):
            return direct.iloc[0].district_id
        mapped=read_frame('''SELECT DISTINCT d.district_id FROM legacy_district_ids l JOIN districts d ON d.district_id=l.canonical_id
            WHERE l.legacy_id=%s''',connection,(district_id,))
        if len(mapped)==1:
            return mapped.iloc[0].district_id
        if len(mapped)>1:
            raise LookupError('Ambiguous district identity.')
        if '-' in district_id:
            state,name=district_id.split('-',1)
            candidate=read_frame('''SELECT district_id FROM districts WHERE LEFT(district_id,3)=%s
                AND LOWER(REPLACE(district_name,' ','_'))=LOWER(%s)''',connection,(state.upper()+'-',name))
            if len(candidate)==1:
                return candidate.iloc[0].district_id
        raise LookupError('Unknown district ID; use a canonical ID or a recorded legacy alias.')
    finally:
        connection.close()

def get_district_metadata(district_id):
    connection=get_connection()
    try:
        rows=read_frame('SELECT district_name AS name,state,agro_climatic_zone FROM districts WHERE district_id=%s',connection,(district_id,))
        if rows.empty:
            raise LookupError('Unknown canonical district ID.')
        return rows.iloc[0].to_dict()
    finally:
        connection.close()
