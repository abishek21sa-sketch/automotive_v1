"""County-level road network resilience ranking.

Real Census Bureau county adjacency data (physically bordering counties,
a reasonable proxy for the road network's coarse topology — the same kind
of stated-proxy honesty airlinesapp uses for its own graph layer) is built
into a graph, then ranked by betweenness centrality: which counties sit on
the most shortest paths between other counties, i.e. structural bridges in
the national road network.

Betweenness (a structural bridge measure) is kept deliberately separate from
FARS crash volume (an outcome measure) — multiplying them into one score
would imply a validated relationship between "structurally central" and
"dangerous" that hasn't been tested. Both are reported; the reader decides
what they want to look at, same as airlinesapp's Network Resilience Ranking.

Source: https://www2.census.gov/geo/docs/reference/county_adjacency.txt
"""

import json
from pathlib import Path

import duckdb
import networkx as nx
import pandas as pd

RAW_PATH = Path(__file__).resolve().parents[3] / "data" / "raw" / "census" / "county_adjacency.txt"
WAREHOUSE_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse" / "automotive.duckdb"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


def parse_adjacency() -> nx.Graph:
    graph = nx.Graph()
    current_name, current_fips = None, None
    with open(RAW_PATH, encoding="latin-1") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                continue
            name, fips, nbr_name, nbr_fips = parts
            if name.strip('"'):
                current_name, current_fips = name.strip('"'), fips.strip()
            nbr_name, nbr_fips = nbr_name.strip('"'), nbr_fips.strip()
            graph.add_node(current_fips, name=current_name)
            graph.add_node(nbr_fips, name=nbr_name)
            if current_fips != nbr_fips:
                graph.add_edge(current_fips, nbr_fips)
    return graph


def county_crash_counts(con) -> pd.DataFrame:
    return con.execute(
        """
        SELECT
            printf('%02d%03d', CAST(STATE AS INTEGER), CAST(COUNTY AS INTEGER)) AS fips,
            COUNT(*) AS accidents,
            SUM(FATALS) AS fatals
        FROM fars_accident
        WHERE STATE IS NOT NULL AND COUNTY IS NOT NULL
        GROUP BY 1
        """
    ).fetchdf()


def main() -> None:
    print(f"Parsing {RAW_PATH} ...")
    graph = parse_adjacency()
    print(f"Graph: {graph.number_of_nodes()} counties, {graph.number_of_edges()} adjacency edges")

    print("Computing betweenness centrality (this is the slow step) ...")
    betweenness = nx.betweenness_centrality(graph, k=500, seed=42, normalized=True)

    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    crashes = county_crash_counts(con).set_index("fips")
    con.close()

    rows = []
    for fips, score in betweenness.items():
        name = graph.nodes[fips].get("name")
        if not name:
            continue
        crash_row = crashes.loc[fips] if fips in crashes.index else None
        rows.append({
            "fips": fips,
            "county": name,
            "betweenness_centrality": round(score, 5),
            "degree": graph.degree[fips],
            "fatal_accidents_2018_2024": int(crash_row["accidents"]) if crash_row is not None else 0,
            "fatalities_2018_2024": int(crash_row["fatals"]) if crash_row is not None else 0,
        })

    rows.sort(key=lambda r: r["betweenness_centrality"], reverse=True)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / "county_network.json"
    with open(out_path, "w") as f:
        json.dump({
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "betweenness_approximation_k": 500,
            "counties": rows,
        }, f, indent=2)

    print(f"Top 10 by betweenness centrality:")
    for r in rows[:10]:
        print(f"  {r['county']:35s} betweenness={r['betweenness_centrality']:.4f}  "
              f"degree={r['degree']:3d}  fatal_accidents={r['fatal_accidents_2018_2024']}")
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
