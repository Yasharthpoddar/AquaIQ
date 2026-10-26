"""Read-only aggregate fingerprints proving isolated experiments preserve public data."""
import argparse
import json
from pathlib import Path

from psycopg2 import sql
from db.connection import get_connection


def fingerprint():
    conn = get_connection()
    result = {}
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")
                tables = [row[0] for row in cur.fetchall()]
                for table in tables:
                    cur.execute(sql.SQL("SELECT COUNT(*), md5(COALESCE(string_agg(digest, '' ORDER BY digest), '')) FROM (SELECT md5(row_to_json(t)::text) AS digest FROM public.{} t) fingerprints").format(sql.Identifier(table)))
                    count, digest = cur.fetchone()
                    result[table] = {'rows': count, 'content_md5_of_sorted_row_hashes': digest}
    finally:
        conn.close()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    current = fingerprint()
    if args.compare and json.loads(args.compare.read_text(encoding='utf-8')) != current:
        raise RuntimeError('Public table fingerprints changed since the recorded snapshot.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(current, indent=2)+'\n', encoding='utf-8')
    print(f'Read-only fingerprints saved for {len(current)} public tables; compared={args.compare is not None}.')
