"""
GET /api/history/<district_id>
Returns historical GWL + rainfall data for a district.
"""

from flask import Blueprint, jsonify, request
from models.ensemble import get_connection
import pandas as pd

history_bp = Blueprint("history", __name__)


@history_bp.route("/history/<district_id>", methods=["GET"])
def get_history(district_id):
    """
    Query params: ?start=2020-01&end=2024-12
    Response:
    {
      "district_id": "RJ-Jaipur",
      "data": [
        {"date": "2024-01", "gwl": 7.2, "rainfall": 12.5},
        ...
      ]
    }
    """
    start = request.args.get("start", "2020-01")
    end = request.args.get("end", "2024-12")

    try:
        conn = get_connection()
        query = """
            SELECT to_char(date, 'YYYY-MM') as month, gwl_current as gwl, rainfall_current as rainfall
            FROM features
            WHERE district_id = %s AND date >= %s AND date <= %s
            ORDER BY date
        """
        # Append -01 to YYYY-MM for the DB date format
        start_date = f"{start}-01" if len(start) == 7 else start
        end_date = f"{end}-28" if len(end) == 7 else end # simplified end date logic
        
        df = pd.read_sql(query, conn, params=(district_id, start_date, end_date))
        conn.close()
        
        data = df.to_dict(orient="records") if len(df) > 0 else []
        
        return jsonify({
            "district_id": district_id,
            "start": start,
            "end": end,
            "data": data,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
