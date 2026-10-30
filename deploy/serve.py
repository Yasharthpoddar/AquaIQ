"""Readiness-gated Waitress entry point for an already restored AquaIQ release."""
from __future__ import annotations

import os


def validate_environment(environ=None):
    """Refuse development credentials and the example file's placeholders."""
    settings = os.environ if environ is None else environ
    forbidden = {"aquaiq-dev-key", "replace_with_private_random_value", "replace_locally",
                 "change_me", "changeme", "password", "your_password", "your_secret_key"}
    for name in ("SECRET_KEY", "POSTGRES_PASSWORD"):
        value = settings.get(name, "")
        if (not isinstance(value, str) or not value or value != value.strip()
                or value.lower() in forbidden or value.lower().startswith(("replace_", "your_"))
                or (name == "SECRET_KEY" and len(value) < 32)):
            raise ValueError("Configure private non-placeholder SECRET_KEY and PostgreSQL credentials")


def validate_release(app, expected_districts=725):
    """Reject absent/mismatched data and an empty or incomplete score publication."""
    if not isinstance(expected_districts, int) or isinstance(expected_districts, bool) or expected_districts < 1:
        raise ValueError("Expected district count must be a positive integer")
    from db.connection import get_connection
    from models.ensemble import feature_generation

    client = app.test_client()
    health = client.get("/api/health")
    if health.status_code != 200 or health.json.get("status") != "healthy":
        raise RuntimeError("Database and all three matching model bundles must pass /api/health")
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM districts")
            district_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*), COUNT(DISTINCT district_id) FROM features WHERE feature_generation=%s",
                           (feature_generation(),))
            feature_rows, feature_districts = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM raw_data")
            raw_rows = cursor.fetchone()[0]
        if (district_count != expected_districts or feature_districts != expected_districts
                or feature_rows < expected_districts or raw_rows < 1):
            raise RuntimeError("Restore the complete matching district/raw/feature database before serving")
    finally:
        connection.close()
    scores = client.get("/api/scores")
    if (scores.status_code != 200 or scores.json.get("status") != "success"
            or scores.json.get("total") != expected_districts
            or len(scores.json.get("districts", [])) != expected_districts):
        raise RuntimeError("A complete scoring run matching configuration, model and feature generation is required")
    return {"districts": district_count, "feature_rows": feature_rows,
            "raw_rows": raw_rows, "scores": scores.json["total"]}


def main():
    from dotenv import load_dotenv
    load_dotenv(override=False)
    try:
        validate_environment()
    except ValueError as error:
        raise SystemExit(str(error)) from None
    from api.app import create_app
    from waitress import serve
    app = create_app()
    try:
        validate_release(app, int(os.getenv("AQUAIQ_EXPECTED_DISTRICTS", "725")))
        if os.getenv('AQUAIQ_REQUIRE_STATE_MEDIAN_RELEASE', 'false').lower() == 'true':
            validate_state_median_release(app)
    except Exception as error:
        # Do not dump credentials, source values or response payloads into logs.
        raise SystemExit(f"AquaIQ release readiness failed ({type(error).__name__}). Check restored data, bundles, /api/health and the exact median artifact/publication/runtime settings.") from None
    serve(app, host="0.0.0.0", port=5000, threads=4, channel_timeout=180,
          max_request_body_size=32768, expose_tracebacks=False)


def validate_state_median_release(app):
    """Read-only readiness: exact local artifact and complete pinned publication."""
    from models.state_median_release import verify_release
    from models.state_median_release_storage import get_published_manifest
    from models.state_median_storage import validate_generation
    directory = os.getenv('AQUAIQ_STATE_MEDIAN_ARTIFACT_DIR')
    expected = os.getenv('AQUAIQ_STATE_MEDIAN_EXPECTED_RELEASE')
    signature = os.getenv('AQUAIQ_STATE_MEDIAN_MANIFEST_SHA256')
    if not directory or not expected or not signature:
        raise RuntimeError('Configure the median artifact directory, expected release and manifest SHA-256.')
    _, _, manifest, _ = verify_release(directory, expected, signature)
    if get_published_manifest() != manifest:
        raise RuntimeError('Published state median manifest differs from the exact runtime artifact.')
    client = app.test_client()
    summary = client.get('/api/v2/states/summary')
    if summary.status_code != 200 or summary.json.get('artifact_release') != expected:
        raise RuntimeError('No matching primary median States publication is ready.')
    payloads = {}
    for state in summary.json['states']:
        response = client.get('/api/v2/predict/state/' + state['state_id'],
            query_string={'generation_id': summary.json['generation_id'], 'as_of': summary.json['as_of']})
        if response.status_code != 200:
            raise RuntimeError('A primary median state response is unavailable or corrupt.')
        payloads[state['state_id']] = response.json
    validate_generation(payloads)
    return dict(generation_id=summary.json['generation_id'], artifact_release=expected,
                states=len(payloads), available=summary.json['available_states_count'])


if __name__ == "__main__":
    main()
