"""Compatibility access to the same observed monitoring readiness used in serving.

Readiness uses configured monitoring rounds and the requested evidence cutoff.
It is separate from the monthly projection's minimum history/span requirement.
"""
import pandas as pd

from db.connection import get_connection, read_frame
from models.ensemble import select_evidence


def get_zone_aggregate_data(zone: str, conn=None) -> pd.DataFrame:
    """Return measured groundwater by month; duplicates cannot inflate coverage."""
    own = conn is None
    conn = conn or get_connection()
    try:
        return read_frame("""
            SELECT r.date, AVG(r.value) AS gwl_mean,
                   COUNT(DISTINCT r.district_id) AS reporting_districts
            FROM raw_data r JOIN districts d ON r.district_id=d.district_id
            WHERE d.agro_climatic_zone=%s AND r.source='CGWB' AND r.metric='GWL'
            GROUP BY r.date ORDER BY r.date
        """, conn, (zone,))
    finally:
        if own:
            conn.close()


def get_data_readiness(district_id: str, as_of=None) -> dict:
    """Expose serving readiness rather than a second hardcoded monthly formula.

    Unknown districts and unavailable databases retain their explicit errors;
    a failed query must not silently become a measured zero-percent readiness.
    """
    evidence = select_evidence(district_id, as_of)
    readiness = evidence['readiness']
    zone = readiness.get('zone_readiness', {})
    fallback = evidence['estimate_type'] == 'zone_fallback'
    return {
        'district_id': district_id,
        **readiness,
        'cgwb_months': readiness['observed_months'],
        'is_zone_fallback': fallback,
        'estimate_type': evidence['estimate_type'],
        'fallback_zone': evidence['zone'] if fallback else None,
        'zone_months': zone.get('observed_months') if fallback else None,
        'zone_reporting_districts': int(evidence['frame'].reporting_districts.max())
            if fallback and 'reporting_districts' in evidence['frame'] and len(evidence['frame']) else None,
    }
