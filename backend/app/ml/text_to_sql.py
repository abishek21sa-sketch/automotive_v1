"""Natural-language question -> SQL -> real warehouse data -> plain-English
answer, grounded in the same methodology notes used elsewhere in this app so
the assistant can't misrepresent what the numbers mean (e.g. it's told FARS
covers fatal crashes only, and that VMT-normalized rates tell a different
story than raw counts, before it ever sees the user's question).

Safety: the DuckDB connection here is opened read-only (defense #1 — the
engine itself rejects DDL/DML). The generated SQL is additionally checked
against a keyword denylist (defense #2) and only ever a single SELECT
statement is allowed to run. Results are capped at MAX_ROWS regardless of
what the model asks for.
"""

import re

import duckdb

from app.services.gemini_client import MODEL, get_client
from app.services.warehouse import get_connection

MAX_ROWS = 200

SCHEMA_DESCRIPTION = """
fars_accident — one row per real fatal crash, NHTSA FARS, 2018-2024 (256,614 rows).
  Only FATAL crashes are in FARS — there is no non-fatal crash data anywhere
  in this warehouse, so counts here are fatal-crash counts, not "all crashes."
  Columns: data_year (int), STATE (numeric FIPS-ish code), STATENAME (text,
  e.g. 'California'), COUNTY (int, county code within state), COUNTYNAME,
  MONTH, DAY, DAY_WEEKNAME, FATALS (int, deaths in this crash), LATITUDE,
  LONGITUD, NHS (1 if on National Highway System), ROUTENAME, FUNC_SYSNAME
  (road functional class).

fars_vehicle — one row per vehicle involved in a fatal crash (395,547 rows).
  Columns include data_year, STATE, MAKE/MAKENAME, MODEL/MODELNAME (may be
  sparsely populated/coded), TRAV_SP (travel speed), VSPD_LIM (speed limit),
  BODY_TYPNAME.

fars_person — one row per person involved in a fatal crash (628,374 rows).
  Columns include data_year, STATE, AGE, SEXNAME, INJ_SEVNAME (injury
  severity), PER_TYPNAME (driver/passenger/pedestrian/etc.).

nhtsa_complaints — real NHTSA consumer complaints (VOQ), free text, filtered
  to LDATE >= 2018 (805,882 rows). Self-reported by consumers, not verified
  defects — a spike in complaints is a signal worth investigating, not
  proof of a defect.
  Columns: MFR_NAME, MAKETXT, MODELTXT, YEARTXT (model year, text),
  CRASH ('Y'/'N'), FIRE ('Y'/'N'), INJURED (int), DEATHS (int), COMPDESC
  (component description, e.g. 'ENGINE', 'STEERING'), STATE (2-letter),
  LDATE (complaint-received date, format YYYYMMDD as text), MILES (mileage
  at failure), CDESCR (free-text complaint description).

fhwa_state_vmt — real FHWA Highway Statistics Table VM-2, state-level annual
  vehicle-miles traveled by functional system, 2018-2024 (358 rows, one per
  state-year). This is the EXPOSURE denominator: a state with more crashes
  isn't necessarily more dangerous if it also has proportionally more
  driving — always consider normalizing crash/complaint counts by
  total_vmt_millions when a question is about relative danger or ranking,
  not raw volume.
  Columns: state (full name, e.g. 'California'), year, rural_vmt_millions,
  urban_vmt_millions, total_vmt_millions.

afdc_stations — real DOE Alternative Fuels Data Center EV charging stations,
  current snapshot, not historical (89,161 rows).
  Columns: station_name, fuel_type_code (filter to 'ELEC' for EV), status_code
  ('E' = available/open — filter to this for "currently operating" questions),
  latitude, longitude, city, state (2-letter code — NOT the same format as
  fhwa_state_vmt.state, which is a full name), ev_network (operator, e.g.
  'Tesla', 'ChargePoint'), ev_dc_fast_num, ev_level2_evse_num (port counts),
  open_date.

Joining fhwa_state_vmt to fars_accident/afdc_stations requires matching
state name formats — fars_accident.STATENAME and fhwa_state_vmt.state are
both full names ('California'); afdc_stations.state is a 2-letter code and
has no direct join key in this schema without a lookup table.
"""

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|COPY|PRAGMA|"
    r"CALL|EXPORT|IMPORT|INSTALL|LOAD|SET|VACUUM)\b",
    re.IGNORECASE,
)


def _extract_sql(text: str) -> str:
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    sql = match.group(1) if match else text
    return sql.strip().rstrip(";")


def _validate_sql(sql: str) -> None:
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError("Generated query must be a single SELECT statement")
    if ";" in sql:
        raise ValueError("Multiple statements are not allowed")
    if FORBIDDEN_KEYWORDS.search(sql):
        raise ValueError("Generated query contains a disallowed keyword")


def answer_question(question: str) -> dict:
    client = get_client()

    sql_prompt = f"""You are a DuckDB SQL generator for a road-safety and vehicle-reliability data warehouse.

Schema:
{SCHEMA_DESCRIPTION}

Rules:
- Output ONLY a single SELECT statement in a ```sql code block. No prose, no explanation.
- Never write INSERT/UPDATE/DELETE/DROP/ALTER or any statement other than SELECT.
- Always add a LIMIT clause (<= {MAX_ROWS}) unless the question clearly wants a single aggregate row.
- If the question is about "which state/model is most dangerous/best/worst" and total_vmt_millions or complaint volume context is available and relevant, prefer a normalized rate over a raw count, or compute both.

Question: {question}"""

    sql_response = client.models.generate_content(model=MODEL, contents=sql_prompt)
    sql = _extract_sql(sql_response.text)
    _validate_sql(sql)

    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        sql = f"{sql} LIMIT {MAX_ROWS}"

    con = get_connection()
    try:
        result = con.execute(sql)
        columns = [d[0] for d in result.description]
        rows = result.fetchmany(MAX_ROWS)
    except duckdb.Error as e:
        return {
            "question": question,
            "generated_sql": sql,
            "error": f"Query failed: {e}",
            "columns": [],
            "rows": [],
            "summary": None,
        }

    row_dicts = [dict(zip(columns, r)) for r in rows]

    summary_prompt = f"""You answered this question by running SQL against a real
NHTSA/FHWA/DOE warehouse (FARS covers FATAL crashes only; complaints are
self-reported, not verified defects; always mention if a ranking used raw
counts rather than a rate normalized by driving volume, when that distinction
matters to the answer).

Question: {question}
SQL run: {sql}
Result ({len(row_dicts)} rows, showing up to 10): {row_dicts[:10]}

Write a 2-4 sentence plain-English answer. State any real limitation of the
data that's relevant to this specific question (don't recite generic
disclaimers that don't apply)."""

    summary_response = client.models.generate_content(model=MODEL, contents=summary_prompt)

    return {
        "question": question,
        "generated_sql": sql,
        "error": None,
        "columns": columns,
        "rows": row_dicts,
        "summary": summary_response.text.strip(),
    }
