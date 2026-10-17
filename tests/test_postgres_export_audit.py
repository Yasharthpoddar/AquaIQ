import pytest
from scripts.audit_postgres_export import inspect_copy


def test_export_inspection_counts_historical_rows_without_interpreting_as_current():
    actual = inspect_copy(iter([
        'COPY public.raw_data (district_id, date, value) FROM stdin;\n',
        '7\t2020-01-01\t8\n', '7\t2020-02-01\t\\N\n', '\\.\n']))['public.raw_data']
    assert actual['rows'] == 2 and actual['districts'] == 1
    assert actual['numeric_district_ids'] == 1
    assert actual['missing_counts']['value'] == 1
    assert actual['date_start'] == '2020-01-01' and actual['date_end'] == '2020-02-01'


def test_truncated_export_is_not_reported_as_complete():
    with pytest.raises(ValueError, match='Truncated'):
        inspect_copy(iter(['COPY public.districts (district_id) FROM stdin;\n', '7\n']))
