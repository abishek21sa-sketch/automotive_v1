from fastapi import APIRouter, Query

from app.services.warehouse import get_connection

router = APIRouter(prefix="/api/warehouse", tags=["warehouse"])


@router.get("/tables")
def list_tables() -> list[dict]:
    con = get_connection()
    rows = con.execute(
        "SELECT table_name, estimated_size AS row_count "
        "FROM duckdb_tables() ORDER BY table_name"
    ).fetchall()
    return [{"table": r[0], "row_count": r[1]} for r in rows]


@router.get("/crashes/by-year")
def crashes_by_year() -> list[dict]:
    con = get_connection()
    rows = con.execute(
        "SELECT data_year, COUNT(*) AS accidents "
        "FROM fars_accident GROUP BY data_year ORDER BY data_year"
    ).fetchall()
    return [{"year": r[0], "accidents": r[1]} for r in rows]


@router.get("/crashes/points")
def crash_points(year: int = Query(2024, ge=2018, le=2024)) -> dict:
    """Real FARS fatal-crash locations for one year, as GeoJSON.

    FARS's public LATITUDE/LONGITUD sentinel values (77.7777/777.7777 etc.)
    mark "unknown" — those rows are excluded rather than plotted at (0,0)
    or wherever the sentinel decodes to.
    """
    con = get_connection()
    rows = con.execute(
        """
        SELECT LATITUDE, LONGITUD, FATALS, STATENAME
        FROM fars_accident
        WHERE data_year = ?
          AND LATITUDE BETWEEN -90 AND 90
          AND LONGITUD BETWEEN -180 AND 180
          AND LATITUDE != 0 AND LONGITUD != 0
        """,
        [year],
    ).fetchall()
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"fatals": fatals, "state": state},
        }
        for lat, lon, fatals, state in rows
    ]
    return {"type": "FeatureCollection", "features": features}


@router.get("/crashes/rate-per-vmt")
def crashes_per_vmt(year: int = Query(2023, ge=2018, le=2023)) -> list[dict]:
    """Fatal crashes per 100 million vehicle-miles traveled, by state —
    real FHWA Highway Statistics Table VM-2 as the exposure denominator,
    not raw crash counts. This is the automotive analog of airlinesapp's
    T-100 flight-volume normalization: a state with more crashes isn't
    necessarily more dangerous if it also has proportionally more driving.
    2024 FARS is available but 2024 VM-2 naïve join works too; capped at
    2023 here only because that's the last year both sides are final.
    """
    con = get_connection()
    rows = con.execute(
        """
        SELECT
            a.STATENAME AS state,
            COUNT(*) AS fatal_accidents,
            SUM(a.FATALS) AS fatalities,
            v.total_vmt_millions,
            COUNT(*) / (v.total_vmt_millions / 100.0) AS accidents_per_100m_vmt
        FROM fars_accident a
        JOIN fhwa_state_vmt v
          ON UPPER(a.STATENAME) = UPPER(v.state) AND v.year = a.data_year
        WHERE a.data_year = ?
        GROUP BY a.STATENAME, v.total_vmt_millions
        ORDER BY accidents_per_100m_vmt DESC
        """,
        [year],
    ).fetchall()
    return [
        {
            "state": r[0],
            "fatal_accidents": r[1],
            "fatalities": r[2],
            "total_vmt_millions": round(r[3], 1),
            "accidents_per_100m_vmt": round(r[4], 3),
        }
        for r in rows
    ]


@router.get("/ev/readiness")
def ev_readiness(year: int = Query(2023, ge=2018, le=2023)) -> list[dict]:
    """EV-charging infrastructure per unit of real driving demand, by state:
    public charging ports per billion vehicle-miles traveled (FHWA VM-2 as
    the demand denominator, same discipline as the crash-rate-per-VMT
    endpoint). A state with more stations isn't necessarily better-served if
    it also has proportionally more driving to support."""
    con = get_connection()
    rows = con.execute(
        """
        SELECT
            v.state,
            COUNT(*) AS station_count,
            SUM(COALESCE(a.ev_level2_evse_num, 0) + COALESCE(a.ev_dc_fast_num, 0)) AS port_count,
            v.total_vmt_millions,
            SUM(COALESCE(a.ev_level2_evse_num, 0) + COALESCE(a.ev_dc_fast_num, 0))
              / (v.total_vmt_millions / 1000.0) AS ports_per_billion_vmt
        FROM afdc_stations a
        JOIN state_abbr_lookup l ON UPPER(a.state) = l.abbr
        JOIN fhwa_state_vmt v
          ON UPPER(l.name) = UPPER(v.state) AND v.year = ?
        WHERE a.fuel_type_code = 'ELEC' AND a.status_code = 'E'
        GROUP BY v.state, v.total_vmt_millions
        ORDER BY ports_per_billion_vmt ASC
        """,
        [year],
    ).fetchall()
    return [
        {
            "state": r[0],
            "station_count": r[1],
            "port_count": int(r[2]),
            "total_vmt_millions": round(r[3], 1),
            "ports_per_billion_vmt": round(r[4], 2),
        }
        for r in rows
    ]


@router.get("/ev/stations")
def ev_stations(state: str | None = Query(None)) -> dict:
    """Real AFDC electric-charging station locations, as GeoJSON. Optionally
    filtered to one state (postal code, e.g. 'CA') to keep payloads small —
    the full national set is ~87k points."""
    con = get_connection()
    query = """
        SELECT latitude, longitude, station_name, ev_network,
               ev_dc_fast_num, ev_level2_evse_num
        FROM afdc_stations
        WHERE fuel_type_code = 'ELEC' AND status_code = 'E'
          AND latitude IS NOT NULL AND longitude IS NOT NULL
    """
    params = []
    if state:
        query += " AND UPPER(state) = UPPER(?)"
        params.append(state)
    rows = con.execute(query, params).fetchall()
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": name,
                "network": network,
                "dc_fast": dc_fast or 0,
                "level2": level2 or 0,
            },
        }
        for lat, lon, name, network, dc_fast, level2 in rows
    ]
    return {"type": "FeatureCollection", "features": features}
