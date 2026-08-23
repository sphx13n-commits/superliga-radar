import base64
import json
import os
import time
from datetime import date, datetime
from pathlib import Path

import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="Superliga Radar", layout="centered")

NAVY = "#0B1F3A"
NAVY_SOFT = "rgba(11, 31, 58, 0.36)"
GRID = "#B8C7D9"
AXIS = "#6B82A0"
BG = "#EEF2F7"
WHITE = "#FFFFFF"
MINUTES_TYPE_ID = 119
LEAGUE_ID = 271
CACHE_ROOT = Path(__file__).with_name("cache") / "superliga"
POSITION_MAP = {24: "GK", 25: "DEF", 26: "MID", 27: "FWD"}

POSITION_METRICS = {
    "GK": [
        {"key": "saves_p90", "label": "Saves/90", "tid": 57, "kind": "per90"},
        {"key": "saves_box_p90", "label": "Saves Box/90", "tid": 104, "kind": "per90"},
        {"key": "conceded_p90", "label": "Conc./90", "tid": 88, "kind": "lower_better_per90"},
        {"key": "pass_acc", "label": "Pass Acc %", "kind": "ratio", "num": 116, "den": 80},
        {"key": "acc_pass_p90", "label": "Acc Pass/90", "tid": 116, "kind": "per90"},
        {"key": "long_p90", "label": "Long Balls/90", "tid": 122, "kind": "per90"},
        {"key": "recovery_p90", "label": "Recovery/90", "tid": 27271, "kind": "per90"},
    ],
    "DEF": [
        {"key": "tackles_p90", "label": "Tackles/90", "tid": 78, "kind": "per90"},
        {"key": "int_p90", "label": "Intercepts/90", "tid": 100, "kind": "per90"},
        {"key": "clear_p90", "label": "Clearances/90", "tid": 101, "kind": "per90"},
        {"key": "aerial_p90", "label": "Aerials/90", "tid": 107, "kind": "per90"},
        {"key": "pass_acc", "label": "Pass Acc %", "kind": "ratio", "num": 116, "den": 80},
        {"key": "acc_pass_p90", "label": "Acc Pass/90", "tid": 116, "kind": "per90"},
        {"key": "recovery_p90", "label": "Recovery/90", "tid": 27271, "kind": "per90"},
        {"key": "fouls_p90", "label": "Fouls/90", "tid": 56, "kind": "lower_better_per90"},
    ],
    "MID": [
        {"key": "passes_p90", "label": "Passes/90", "tid": 80, "kind": "per90"},
        {"key": "pass_acc", "label": "Pass Acc %", "kind": "ratio", "num": 116, "den": 80},
        {"key": "key_p90", "label": "Key Pass/90", "tid": 117, "kind": "per90"},
        {"key": "assists_p90", "label": "Assists/90", "tid": 79, "kind": "per90"},
        {"key": "tackles_p90", "label": "Tackles/90", "tid": 78, "kind": "per90"},
        {"key": "int_p90", "label": "Intercepts/90", "tid": 100, "kind": "per90"},
        {"key": "succ_drib_p90", "label": "Succ Drib/90", "tid": 109, "kind": "per90"},
        {"key": "recovery_p90", "label": "Recovery/90", "tid": 27271, "kind": "per90"},
    ],
    "FWD": [
        {"key": "goals_p90", "label": "Goals/90", "tid": 52, "kind": "per90"},
        {"key": "assists_p90", "label": "Assists/90", "tid": 79, "kind": "per90"},
        {"key": "shots_p90", "label": "Shots/90", "tid": 42, "kind": "per90"},
        {"key": "sot_p90", "label": "SOT/90", "tid": 86, "kind": "per90"},
        {"key": "key_p90", "label": "Key Pass/90", "tid": 117, "kind": "per90"},
        {"key": "drib_att_p90", "label": "Drib Att/90", "tid": 108, "kind": "per90"},
        {"key": "succ_drib_p90", "label": "Succ Drib/90", "tid": 109, "kind": "per90"},
        {"key": "aerial_p90", "label": "Aerials/90", "tid": 107, "kind": "per90"},
    ],
}

_, lang_col = st.columns([4, 1])
with lang_col:
    language = st.selectbox("Language", ["日本語", "English"], index=0, label_visibility="collapsed")
is_en = language == "English"

st.markdown(
    f"""
    <div style="background:{NAVY};padding:14px 16px 11px;border-radius:12px;margin-bottom:10px;">
      <div style="color:white;font-size:24px;font-weight:750;">Superliga Radar</div>
      <div style="color:#C9D4E3;font-size:12px;margin-top:2px;">
        {"Fixture Aggregate scouting radar" if is_en else "Fixture集計ベースのスカウティングレーダー"}
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

token = os.getenv("SPORTMONKS_TOKEN")
if not token:
    st.error("Token not found" if is_en else "トークンが見つかりません")
    st.stop()

headers = {"Authorization": token}
params = {"api_token": token}
base_url = "https://api.sportmonks.com/v3/football"
default_season_id = 27897


def _deep_num(obj):
    if obj is None or isinstance(obj, bool):
        return None
    if isinstance(obj, (int, float)):
        return float(obj)
    if isinstance(obj, str):
        try:
            return float(obj)
        except ValueError:
            return None
    if isinstance(obj, dict):
        for k in ("total", "minutes", "value", "average", "count", "sum", "percentage"):
            if k in obj:
                n = _deep_num(obj[k])
                if n is not None:
                    return n
        for v in obj.values():
            n = _deep_num(v)
            if n is not None:
                return n
    if isinstance(obj, (list, tuple)):
        for x in obj:
            n = _deep_num(x)
            if n is not None:
                return n
    return None


def _extract_stat(detail):
    if not isinstance(detail, dict):
        return None
    for key in ("data", "value", "values"):
        if key in detail:
            n = _deep_num(detail[key])
            if n is not None:
                return n
    return None


def _cache_dir(sid):
    d = CACHE_ROOT / f"season_{sid}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _is_finished_fixture(fx):
    state = fx.get("state") or {}
    state_id = fx.get("state_id") or state.get("id")
    name = (state.get("short_name") or state.get("name") or state.get("developer_name") or "").upper()
    if state_id in (5, 7, 8):
        return True
    if name in ("FT", "FULL TIME", "FINISHED", "AET", "FT_PEN"):
        return True
    return bool(fx.get("result_info") or fx.get("scores"))


def get_logo_data_uri():
    p = Path(__file__).with_name("logo.png")
    if not p.exists():
        return None
    return f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def build_radar_figure(labels, values, title_lines, radial_max):
    fig = go.Figure(
        go.Scatterpolar(
            r=values + [values[0]],
            theta=labels + [labels[0]],
            fill="toself",
            fillcolor=NAVY_SOFT,
            line={"color": NAVY, "width": 3.5},
            marker={"color": WHITE, "size": 10, "line": {"color": NAVY, "width": 2.5}},
            mode="lines+markers",
        )
    )
    annotations = []
    sizes = [28, 16, 14]
    for i, line in enumerate(title_lines):
        annotations.append(
            {
                "text": f"<b>{line}</b>" if i == 0 else line,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.995 - i * 0.048,
                "xanchor": "center",
                "yanchor": "top",
                "showarrow": False,
                "font": {"color": NAVY, "size": sizes[i] if i < len(sizes) else 13, "family": "Arial"},
            }
        )
    annotations.append(
        {
            "text": "@Dalaprospect",
            "xref": "paper",
            "yref": "paper",
            "x": 0.93,
            "y": 0.01,
            "xanchor": "center",
            "yanchor": "bottom",
            "showarrow": False,
            "font": {"color": NAVY, "size": 12, "family": "Arial"},
        }
    )
    images = []
    logo = get_logo_data_uri()
    if logo:
        images.append(
            {
                "source": logo,
                "xref": "paper",
                "yref": "paper",
                "x": 0.93,
                "y": 0.055,
                "sizex": 0.085,
                "sizey": 0.085,
                "xanchor": "center",
                "yanchor": "bottom",
                "sizing": "contain",
                "layer": "above",
            }
        )
    fig.update_layout(
        height=820,
        margin={"l": 36, "r": 36, "t": 140, "b": 78},
        paper_bgcolor=WHITE,
        plot_bgcolor=WHITE,
        showlegend=False,
        images=images,
        annotations=annotations,
        polar={
            "domain": {"x": [0.02, 0.98], "y": [0.08, 0.74]},
            "bgcolor": BG,
            "radialaxis": {
                "visible": True,
                "range": [0, radial_max],
                "gridcolor": GRID,
                "linecolor": AXIS,
                "tickfont": {"color": AXIS, "size": 12},
            },
            "angularaxis": {
                "gridcolor": GRID,
                "linecolor": AXIS,
                "tickfont": {"color": NAVY, "size": 13},
                "rotation": 90,
                "direction": "clockwise",
            },
        },
    )
    return fig


def percentile_rank(values, target, higher_is_better=True):
    n = len(values)
    if n <= 1:
        return 50.0
    if higher_is_better:
        below = sum(1 for v in values if v < target)
        equal = sum(1 for v in values if v == target)
    else:
        below = sum(1 for v in values if v > target)
        equal = sum(1 for v in values if v == target)
    return round(100.0 * (below + (equal - 1) / 2.0) / (n - 1), 1)


def compute_metrics(raw, minutes, metric_defs):
    out = {}
    for m in metric_defs:
        if m["kind"] in ("per90", "lower_better_per90"):
            out[m["key"]] = (
                round(raw.get(m["tid"], 0.0) * 90.0 / minutes, 3) if minutes > 0 else None
            )
        elif m["kind"] == "ratio":
            den = raw.get(m["den"], 0.0)
            num = raw.get(m["num"], 0.0)
            out[m["key"]] = round(num / den * 100.0, 2) if den > 0 else None
    return out


def _is_finished_fixture(fx):
    state = fx.get("state") or {}
    state_id = fx.get("state_id") or state.get("id")
    name = (state.get("short_name") or state.get("name") or state.get("developer_name") or "").upper()
    if state_id in (5, 7, 8):
        return True
    if name in ("FT", "FULL TIME", "FINISHED", "AET", "FT_PEN"):
        return True
    return bool(fx.get("result_info") or fx.get("scores"))


# ----- season -----
league_res = requests.get(
    f"{base_url}/leagues/{LEAGUE_ID}",
    headers=headers,
    params={**params, "include": "currentSeason;seasons"},
    timeout=30,
)
if league_res.status_code != 200:
    st.error(f"リーグ取得エラー: {league_res.status_code}")
    st.stop()

league = league_res.json().get("data", {})
current_season = league.get("currentseason") or league.get("currentSeason") or {}
season_records = [s for s in league.get("seasons", []) if s.get("id") and s.get("name")]
if not season_records and current_season.get("id"):
    season_records = [current_season]
season_records.sort(
    key=lambda s: (s.get("id") == current_season.get("id"), s.get("starting_at", "")),
    reverse=True,
)
season_options = {s["name"]: s["id"] for s in season_records}
season_meta = {s["id"]: s for s in season_records}
season_names = list(season_options)
default_name = next(
    (s["name"] for s in season_records if s["id"] == default_season_id),
    current_season.get("name", season_names[0]),
)
selected_season_name = st.selectbox(
    "シーズン" if not is_en else "Season",
    season_names,
    index=season_names.index(default_name),
)
season_id = season_options[selected_season_name]
season_name = selected_season_name
season_info = season_meta.get(season_id, {})

teams_res = requests.get(
    f"{base_url}/teams/seasons/{season_id}", headers=headers, params=params, timeout=30
)
teams = teams_res.json().get("data", []) if teams_res.status_code == 200 else []
team_id_to_name = {t.get("id"): t.get("name") for t in teams if t.get("id")}
st.success("Connected" if is_en else "Sportmonksに接続できました")
st.caption(f"{'Season' if is_en else 'シーズン'}: {season_name}")


def fetch_season_fixtures_list(sid, season_meta_row):
    """一覧は常に最新化（終了試合の発見用）。個別fixture詳細は別途。"""
    start = (season_meta_row.get("starting_at") or "2026-07-01")[:10]
    end = (season_meta_row.get("ending_at") or "2027-06-30")[:10]
    today = date.today().isoformat()
    if end > today:
        end = today
    all_fx, page, errors = [], 1, 0
    while True:
        res = requests.get(
            f"{base_url}/fixtures/between/{start}/{end}",
            headers=headers,
            params={
                **params,
                "filters": f"fixtureLeagues:{LEAGUE_ID}",
                "include": "state;participants;scores",
                "page": page,
            },
            timeout=40,
        )
        if res.status_code != 200:
            errors += 1
            break
        body = res.json() or {}
        all_fx.extend(body.get("data") or [])
        if not (body.get("pagination") or {}).get("has_more"):
            break
        page += 1
        if page > 30:
            break
        time.sleep(0.08)
    finished = [fx for fx in all_fx if _is_finished_fixture(fx)]
    payload = {
        "season_id": sid,
        "start": start,
        "end": end,
        "total_fetched": len(all_fx),
        "finished_count": len(finished),
        "list_errors": errors,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "fixtures": [
            {"id": fx.get("id"), "name": fx.get("name"), "starting_at": fx.get("starting_at")}
            for fx in finished
            if fx.get("id")
        ],
    }
    _save_json(_cache_dir(sid) / "fixtures_list.json", payload)
    return payload


def load_fixture_detail(sid, fixture_id, force_refresh=False):
    path = _cache_dir(sid) / f"fixture_{fixture_id}.json"
    if not force_refresh and path.exists():
        cached = _load_json(path)
        if cached is not None:
            return cached, "cache", None
    res = requests.get(
        f"{base_url}/fixtures/{fixture_id}",
        headers=headers,
        params={**params, "include": "lineups.details.type;participants"},
        timeout=45,
    )
    if res.status_code != 200:
        return None, "error", f"HTTP {res.status_code}"
    data = (res.json() or {}).get("data")
    _save_json(path, data)
    time.sleep(0.08)
    return data, "api", None


def aggregate_player_team(fixture_payloads, sid):
    aggs = {}
    for fdata in fixture_payloads:
        if not fdata:
            continue
        for lu in fdata.get("lineups") or []:
            pid, tid = lu.get("player_id"), lu.get("team_id")
            if not pid or not tid:
                continue
            key = f"{sid}_{pid}_{tid}"
            pname = (
                (lu.get("player") or {}).get("name")
                or lu.get("player_name")
                or f"id:{pid}"
            )
            pos_id = lu.get("position_id") or ((lu.get("player") or {}).get("position_id"))
            if key not in aggs:
                aggs[key] = {
                    "season_id": sid,
                    "player_id": pid,
                    "team_id": tid,
                    "player_name": pname,
                    "position_id": pos_id,
                    "minutes": 0.0,
                    "raw": {},
                    "apps": 0,
                }
            else:
                if pname and str(aggs[key]["player_name"]).startswith("id:"):
                    aggs[key]["player_name"] = pname
                if pos_id and not aggs[key]["position_id"]:
                    aggs[key]["position_id"] = pos_id
            played = False
            for d in lu.get("details") or []:
                type_id = d.get("type_id")
                if type_id is None:
                    continue
                parsed = _extract_stat(d)
                if parsed is None:
                    continue
                if type_id == MINUTES_TYPE_ID:
                    aggs[key]["minutes"] += parsed
                    if parsed > 0:
                        played = True
                else:
                    aggs[key]["raw"][type_id] = aggs[key]["raw"].get(type_id, 0.0) + parsed
            if played:
                aggs[key]["apps"] += 1
    return aggs


def restore_aggs_from_file(sid):
    cached = _load_json(_cache_dir(sid) / "player_team_aggregate.json")
    if not cached or not cached.get("players"):
        return None, None
    restored = {}
    for p in cached["players"]:
        key = f"{sid}_{p['player_id']}_{p['team_id']}"
        restored[key] = {
            "season_id": sid,
            "player_id": p["player_id"],
            "team_id": p["team_id"],
            "player_name": p["player_name"],
            "position_id": p.get("position_id"),
            "minutes": float(p.get("minutes") or 0),
            "apps": p.get("apps") or 0,
            "raw": {int(k): v for k, v in (p.get("raw") or {}).items()},
        }
    meta = {
        "fixtures": cached.get("fixtures"),
        "players": len(restored),
        "new_fetched": cached.get("new_fetched", 0),
        "cached_fixtures": cached.get("cached_fixtures"),
        "finished_fixtures": cached.get("finished_fixtures"),
        "aggregate_rebuilt": cached.get("aggregate_rebuilt"),
        "updated_at": cached.get("updated_at"),
        "from_cache_file": True,
    }
    return restored, meta


def save_aggs(sid, aggs, status):
    rows_out = [
        {
            "player_id": a["player_id"],
            "team_id": a["team_id"],
            "player_name": a["player_name"],
            "position_id": a["position_id"],
            "minutes": a["minutes"],
            "apps": a["apps"],
            "raw": {str(k): v for k, v in a["raw"].items()},
        }
        for a in aggs.values()
    ]
    payload = {
        "season_id": sid,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "players": rows_out,
        **status,
    }
    _save_json(_cache_dir(sid) / "player_team_aggregate.json", payload)
    return payload


def incremental_update(sid, season_meta_row, force_all=False):
    """
    1) 終了Fixture一覧を最新化
    2) 既存 fixture_*.json はスキップ
    3) 新規のみAPI取得
    4) 新規あり or Aggregateなし or force → Aggregate再構築
    5) それ以外は既存Aggregate
    """
    cdir = _cache_dir(sid)
    flist = fetch_season_fixtures_list(sid, season_meta_row)
    finished_ids = [f["id"] for f in flist.get("fixtures", [])]
    finished_count = len(finished_ids)

    cached_ids = []
    missing_ids = []
    for fid in finished_ids:
        path = cdir / f"fixture_{fid}.json"
        if path.exists() and not force_all:
            cached_ids.append(fid)
        else:
            missing_ids.append(fid)

    loaded = []
    new_fetched = 0
    errors = []
    # load cached
    for fid in cached_ids:
        data = _load_json(cdir / f"fixture_{fid}.json")
        if data is not None:
            loaded.append(data)
    # fetch new only
    prog = st.progress(0.0) if missing_ids else None
    for i, fid in enumerate(missing_ids):
        data, source, err = load_fixture_detail(sid, fid, force_refresh=force_all)
        if err:
            errors.append({"fixture_id": fid, "error": err})
        elif data is not None:
            loaded.append(data)
            if source == "api":
                new_fetched += 1
        if prog:
            prog.progress((i + 1) / max(len(missing_ids), 1))

    agg_path = cdir / "player_team_aggregate.json"
    need_rebuild = force_all or new_fetched > 0 or (not agg_path.exists()) or (len(loaded) == 0 and finished_count > 0 and not agg_path.exists())

    # 既存Aggregateがあり新規0なら再構築しない
    if not need_rebuild and agg_path.exists():
        aggs, meta = restore_aggs_from_file(sid)
        if aggs is not None:
            status = {
                "finished_fixtures": finished_count,
                "cached_fixtures": len(cached_ids),
                "new_fetched": 0,
                "loaded_fixtures": len(loaded),
                "errors": len(errors),
                "aggregate_rebuilt": False,
                "players": len(aggs),
                "updated_at": meta.get("updated_at") if meta else None,
                "mode": "incremental_skip_rebuild",
            }
            return aggs, status, errors

    aggs = aggregate_player_team(loaded, sid)
    status = {
        "finished_fixtures": finished_count,
        "cached_fixtures": len(cached_ids),
        "new_fetched": new_fetched,
        "loaded_fixtures": len(loaded),
        "errors": len(errors),
        "aggregate_rebuilt": True,
        "players": len(aggs),
        "fixtures": len(loaded),
        "mode": "rebuild",
    }
    save_aggs(sid, aggs, status)
    return aggs, status, errors


# ----- UI: update controls -----
c1, c2 = st.columns([2, 1])
with c1:
    force_all = st.checkbox(
        "全Fixtureを強制再取得（通常は不要）" if not is_en else "Force re-fetch all fixtures",
        value=False,
    )
with c2:
    min_min = st.selectbox("最低出場分" if not is_en else "Min minutes", [0, 300, 600, 900], index=1)

run = st.button("データ更新（増分）" if not is_en else "Update data (incremental)", type="primary")

if run:
    with st.spinner("増分更新中..." if not is_en else "Incremental update..."):
        aggs, status, errors = incremental_update(season_id, season_info, force_all=force_all)
        st.session_state.fx_aggs = aggs
        st.session_state.fx_status = status
        st.session_state.fx_errors = errors
        if status.get("aggregate_rebuilt"):
            st.success(
                f"Aggregate再構築 · 新規Fixture {status.get('new_fetched', 0)} · 選手 {status.get('players', 0)}"
            )
        else:
            st.success(
                f"新規なし · 既存Aggregateを使用 · 選手 {status.get('players', 0)}"
            )

# auto restore on load
if "fx_aggs" not in st.session_state or st.session_state.fx_aggs is None:
    aggs, meta = restore_aggs_from_file(season_id)
    if aggs is not None:
        st.session_state.fx_aggs = aggs
        st.session_state.fx_status = meta or {"from_cache_file": True, "players": len(aggs)}
    else:
        # キャッシュ無し → 自動で増分構築
        with st.spinner("初回データ構築中..."):
            aggs, status, errors = incremental_update(season_id, season_info, force_all=False)
            st.session_state.fx_aggs = aggs
            st.session_state.fx_status = status
            st.session_state.fx_errors = errors

aggs = st.session_state.get("fx_aggs")
status = st.session_state.get("fx_status") or {}
errors = st.session_state.get("fx_errors") or []

if not aggs:
    st.warning("データがありません。「データ更新」を押してください。")
    st.stop()

with st.expander("データ更新ステータス" if not is_en else "Update status", expanded=False):
    st.write(
        {
            "終了済みFixture数": status.get("finished_fixtures"),
            "キャッシュ済みFixture数": status.get("cached_fixtures"),
            "今回新規取得": status.get("new_fetched"),
            "読込Fixture数": status.get("loaded_fixtures") or status.get("fixtures"),
            "Aggregate再構築": status.get("aggregate_rebuilt"),
            "選手数": status.get("players") or len(aggs),
            "最終更新": status.get("updated_at"),
            "mode": status.get("mode") or ("cache_file" if status.get("from_cache_file") else None),
            "errors": status.get("errors") or len(errors),
        }
    )
    if errors:
        st.dataframe(errors, use_container_width=True, hide_index=True)

# ----- percentile & UI (unchanged logic) -----
by_pos = {p: [] for p in ("GK", "DEF", "MID", "FWD")}
for a in aggs.values():
    mins = a["minutes"]
    if mins < float(min_min) or mins <= 0:
        continue
    pos = POSITION_MAP.get(a["position_id"])
    if pos not in by_pos:
        continue
    metrics = compute_metrics(a["raw"], mins, POSITION_METRICS[pos])
    by_pos[pos].append(
        {
            "Player": a["player_name"],
            "Team": team_id_to_name.get(a["team_id"], a["team_id"]),
            "Pos": pos,
            "Minutes": int(round(mins)),
            "Apps": a["apps"],
            "metrics": metrics,
            "raw": a["raw"],
        }
    )

for pos, group in by_pos.items():
    for m in POSITION_METRICS[pos]:
        vals = [g["metrics"][m["key"]] for g in group if g["metrics"].get(m["key"]) is not None]
        higher = m["kind"] != "lower_better_per90"
        for g in group:
            v = g["metrics"].get(m["key"])
            g.setdefault("pct", {})[m["key"]] = (
                None if v is None else percentile_rank(vals, v, higher)
            )

st.caption(
    f"Players(filter): {sum(len(v) for v in by_pos.values())} · "
    f"GK{len(by_pos['GK'])}/DEF{len(by_pos['DEF'])}/MID{len(by_pos['MID'])}/FWD{len(by_pos['FWD'])}"
)

all_players = [g for pos in by_pos.values() for g in pos]
teams_in = sorted({g["Team"] for g in all_players if g["Team"]})
team_filter = st.selectbox(
    "チーム絞り込み" if not is_en else "Team filter",
    (["すべて"] if not is_en else ["All"]) + teams_in,
)
if team_filter not in ("すべて", "All"):
    all_players = [g for g in all_players if g["Team"] == team_filter]

if not all_players:
    st.warning("該当選手がいません。")
    st.stop()

all_players.sort(key=lambda g: (g["Team"], g["Player"]))
labels = [f"{g['Player']} | {g['Team']} | {g['Pos']} | {g['Minutes']}min" for g in all_players]
choice = st.selectbox("選手" if not is_en else "Player", labels)
selected = all_players[labels.index(choice)]
pos = selected["Pos"]
mdefs = POSITION_METRICS[pos]

st.markdown(
    f"**{selected['Player']}** · {selected['Team']} · **{pos}** · {selected['Minutes']} min · Apps {selected['Apps']}"
)

check_rows, radar_labels, radar_values = [], [], []
for m in mdefs:
    if m["kind"] in ("per90", "lower_better_per90"):
        raw_v = selected["raw"].get(m["tid"], 0)
    else:
        raw_v = f"{selected['raw'].get(m['num'], 0)} / {selected['raw'].get(m['den'], 0)}"
    pct = selected.get("pct", {}).get(m["key"])
    check_rows.append(
        {
            "Metric": m["label"],
            "Raw": raw_v,
            "Per90 / %": selected["metrics"].get(m["key"]),
            "Percentile": pct,
        }
    )
    radar_labels.append(m["label"])
    radar_values.append(pct if pct is not None else 0)

st.dataframe(check_rows, use_container_width=True, hide_index=True)

if radar_labels:
    fig = build_radar_figure(
        radar_labels,
        radar_values,
        [
            selected["Player"],
            f"{selected['Team']} | {pos} | {selected['Minutes']} min",
            f"Superliga {season_name} · Fixture Aggregate · Percentile",
        ],
        100,
    )
    try:
        png = fig.to_image(format="png", width=900, height=1180, scale=2)
        st.image(png, use_container_width=True)
        st.download_button(
            "PNGをダウンロード" if not is_en else "Download PNG",
            data=png,
            file_name=f"{selected['Player']}_radar.png",
            mime="image/png",
        )
    except Exception as e:
        st.warning(str(e))
