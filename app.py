from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import pandas as pd
import uvicorn

app = FastAPI()


# Data layer 

def _load():
    peak_df = pd.read_csv("fighter_peak_elo.csv")
    current_df = pd.read_csv("current_fighters_elo.csv")
    fights_df = pd.read_csv("newufcfights.csv")

    peak_elo = dict(zip(peak_df.iloc[:, 0], peak_df.iloc[:, 1]))
    current_elo = dict(zip(current_df.iloc[:, 0], current_df.iloc[:, 1]))

    # CSV is newest-first; reverse so we replay oldest→newest
    fights = fights_df.iloc[::-1].reset_index(drop=True).copy()
    fights["method"] = fights["method"].apply(
        lambda x: "KO" if "KO" in str(x) else ("SUB" if "SUB" in str(x) else str(x).strip())
    )
    fights["result"] = fights["result"].apply(
        lambda x: "nc" if "nc" in str(x).lower() else ("draw" if "draw" in str(x).lower() else str(x).strip())
    )

    elo_ratings: dict[str, float] = {}
    history: dict[str, list] = {}
    records: dict[str, dict] = {}
    base_k, initial = 40, 1000.0

    for _, row in fights.iterrows():
        f1 = str(row["fighter_1"]).strip()
        f2 = str(row["fighter_2"]).strip()
        event = str(row["event"]).strip()
        method = row["method"]
        result = row["result"]

        e1 = elo_ratings.get(f1, initial)
        e2 = elo_ratings.get(f2, initial)
        k = base_k * 1.15 if method in ("KO", "SUB") else float(base_k)

        exp1 = 1 / (1 + 10 ** ((e2 - e1) / 400))

        if result == "win":
            n1 = round(e1 + k * (1 - exp1), 2)
            n2 = round(e2 + k * (0 - (1 - exp1)), 2)
            r1, r2 = "W", "L"
        elif result == "draw":
            n1 = round(e1 + k * (0.5 - exp1), 2)
            n2 = round(e2 + k * (0.5 - (1 - exp1)), 2)
            r1, r2 = "D", "D"
        else:  # nc or anything else → no change
            n1, n2 = e1, e2
            r1, r2 = "NC", "NC"

        elo_ratings[f1], elo_ratings[f2] = n1, n2

        for fighter, before, after, opp, res in [(f1, e1, n1, f2, r1), (f2, e2, n2, f1, r2)]:
            history.setdefault(fighter, []).append(
                {
                    "event": event,
                    "elo": after,
                    "elo_change": round(after - before, 2),
                    "opponent": opp,
                    "result": res,
                    "method": method,
                }
            )
            rec = records.setdefault(fighter, {"W": 0, "L": 0, "D": 0, "NC": 0})
            rec[res] += 1

    return peak_elo, current_elo, history, records, sorted(history.keys())


PEAK_ELO, CURRENT_ELO, ELO_HISTORY, RECORDS, FIGHTER_LIST = _load()
PEAK_RANKED = sorted(PEAK_ELO.items(), key=lambda x: -x[1])
CURRENT_RANKED = sorted(CURRENT_ELO.items(), key=lambda x: -x[1])


def _reload():
    global PEAK_ELO, CURRENT_ELO, ELO_HISTORY, RECORDS, FIGHTER_LIST, PEAK_RANKED, CURRENT_RANKED
    PEAK_ELO, CURRENT_ELO, ELO_HISTORY, RECORDS, FIGHTER_LIST = _load()
    PEAK_RANKED = sorted(PEAK_ELO.items(), key=lambda x: -x[1])
    CURRENT_RANKED = sorted(CURRENT_ELO.items(), key=lambda x: -x[1])


#----------- API -----------#

@app.get("/api/rankings")
def rankings():
    return {
        "peak": [{"rank": i + 1, "fighter": f, "elo": round(e, 2)} for i, (f, e) in enumerate(PEAK_RANKED)],
        "current": [{"rank": i + 1, "fighter": f, "elo": round(e, 2)} for i, (f, e) in enumerate(CURRENT_RANKED)],
    }


@app.get("/api/fighters")
def fighters():
    return FIGHTER_LIST


@app.get("/api/fighter/{name:path}")
def fighter(name: str):
    name = name.strip()
    nl = name.lower()
    matched = next((f for f in FIGHTER_LIST if f.lower() == nl), None)
    if not matched:
        matched = next((f for f in FIGHTER_LIST if nl in f.lower()), None)
    if not matched:
        raise HTTPException(status_code=404, detail=f"Fighter '{name}' not found")

    hist = ELO_HISTORY.get(matched, [])
    rec = RECORDS.get(matched, {"W": 0, "L": 0, "D": 0, "NC": 0})

    start_elo = round(hist[0]["elo"] - hist[0]["elo_change"], 2) if hist else 1000.0
    labels = ["Start"] + [h["event"].split(":")[-1].strip()[:28] for h in hist]
    elo_points = [start_elo] + [h["elo"] for h in hist]

    return {
        "name": matched,
        "current_elo": CURRENT_ELO.get(matched),
        "peak_elo": PEAK_ELO.get(matched),
        "record": rec,
        "fights": list(reversed(hist)),
        "chart": {"labels": labels, "data": elo_points},
    }


@app.post("/api/update")
def update():
    from incremental_scraper import UFCScraper
    result = UFCScraper().run()
    _reload()
    return result


# Frontend 

@app.get("/")
def index():
    return FileResponse("index.html")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
