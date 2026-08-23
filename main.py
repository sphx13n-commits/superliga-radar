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

# ポジション別指標（正しい type_id のみ）
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

_, language_column = st.columns([4, 1])
with language_column:
    language = st.selectbox(
        "Language",
        options=["日本語", "English"],
        index=0,
        label_visibility="collapsed",
    )
is_english = language == "English"

TEXT = {
    "token_missing": "Token not found" if is_english else "トークンが見つかりません",
    "connected": "Connected to Sportmonks" if is_english else "Sportmonksに接続できました",
    "season_select": "Select a season" if is_english else "シーズンを選択",
    "team_select": "Select a team" if is_english else "チームを選択",
    "player_select": "Select a player" if is_english else "選手を選択",
    "minute_filter": "Minutes filter" if is_english else "出場時間",
    "team_list": " squad" if is_english else "の選手一覧",
    "download": "Download PNG" if is_english else "PNGをダウンロード",
    "no_stats": "No stats" if is_english else "この選手のスタッツがありません",
    "all_stats": "Season API stats" if is_english else "シーズンAPIの指標",
    "description": "Superliga radar" if is_english else "スーペルリーガの選手レーダー",
    "season": "Season" if is_english else "シーズン",
}

st.markdown(
    f"""
    <div style="background:{NAVY};padding:14px 16px 11px;border-radius:12px;margin-bottom:10px;">
      <div style="color:white;font-size:24px;font-weight:750;">Superliga Radar</div>
      <div style="color:#C9D4E3;font-size:12px;margin-top:2px;">{TEXT["description"]}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

token = os.getenv("SPORTMONKS_TOKEN")
if not token:
    st.error(TEXT["token_missing"])
    st.stop()

headers = {"Authorization": token}
params = {"api_token": token}
base_url = "https://api.sportmonks.com/v3/football"
default_season_id = 27897
season_id = default_season_id

KNOWN_NAMES = {
    42: ("Shots", "シュート"),
    52: ("Goals", "ゴール"),
    78: ("Tackles", "タックル"),
    79: ("Assists", "アシスト"),
    80: ("Passes", "パス"),
    100: ("Interceptions", "インターセプト"),
    101: ("Clearances", "クリア"),
    107: ("Aerials", "空中戦"),
    109: ("Succ. Dribbles", "ドリブル成功"),
    119: ("Minutes", "出場時間"),
    194: ("Clean sheets", "無失点"),
    214: ("Team wins", "勝利"),
    215: ("Team draws", "引き分け"),
    216: ("Team losses", "敗戦"),
    321: ("Appearances", "出場数"),
    322: ("Lineups", "先発数"),
}
RADAR_ORDER_LEGACY = [52, 79, 42, 78, 100, 101, 107, 109]


def get_total_value(detail):
    for key in ("value", "data"):
        value = detail.get(key)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            for k in ("total", "minutes", "average", "percentage", "value", "count"):
                if k in value and isinstance(value[k], (int, float)):
                    return float(value[k])
            for v in value.values():
                if isinstance(v, (int, float)):
                    return float(v)
    return None


def get_season_statistics(player):
    return [s for s in player.get("statistics", []) if s.get("season_id") == season_id]


def get_minutes(player):
    for statistic in get_season_statistics(player):
        for detail in statistic.get("details", []):
            if detail.get("type_id") == 119:
                value = get_total_value(detail)
                return value if isinstance(value, (int, float)) else 0
    return 0


def calc_age(date_of_birth):
    if not date_of_birth:
        return None
    try:
        born = datetime.strptime(str(date_of_birth)[:10], "%Y-%m-%d").date()
        today = date.today()
        return today.year - born.year - (
            (today.month, today.day) < (born.month, born.day)
        )
    except Exception:
        return None


def get_position_label(player):
    return POSITION_MAP.get(player.get("position_id"), "MID")


def known_name(type_id):
    if type_id in KNOWN_NAMES:
        en, ja = KNOWN_NAMES[type_id]
        return en if is_english else ja
    return f"type_id {type_id}"


def get_logo_data_uri():
    logo_path = Path(__file__).with_name("logo.png")
    if not logo_path.exists():
        return None
    return f"data:image/png;base64,{base64.b64encode(logo_path.read_bytes()).decode('ascii')}"


def build_radar_figure(labels, values, title_lines, radial_max):
    chart_labels = labels + [labels[0]]
    chart_values = values + [values[0]]
    fig = go.Figure(
        go.Scatterpolar(
            r=chart_values,
            theta=chart_labels,
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
                "font": {
                    "color": NAVY,
                    "size": sizes[i] if i < len(sizes) else 13,
                    "family": "Arial",
                },
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
    logo_uri = get_logo_data_uri()
    if logo_uri:
        images.append(
            {
                "source": logo_uri,
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
                "tickfont": {"color": NAVY, "size": 14},
                "rotation": 90,
                "direction": "clockwise",
            },
        },
    )
    return fig


# ========== 既存：シーズンAPIレーダー（非接触） ==========
try:
    league_res = requests.get(
        f"{base_url}/leagues/{LEAGUE_ID}",
        headers=headers,
        params={**params, "include": "currentSeason;seasons"},
        timeout=30,
    )
    league_data = league_res.json()
    if league_res.status_code != 200:
        st.error(f"リーグ取得エラー: {league_res.status_code}")
        st.stop()

    league = league_data.get("data", {})
    current_season = league.get("currentseason") or league.get("currentSeason") or {}
    season_records = [
        s for s in league.get("seasons", []) if s.get("id") and s.get("name")
    ]
    if not season_records and current_season.get("id"):
        season_records = [current_season]
    season_records.sort(
        key=lambda s: (s.get("id") == current_season.get("id"), s.get("starting_at", "")),
        reverse=True,
    )
    season_options = {s["name"]: s["id"] for s in season_records}
    season_meta = {s["id"]: s for s in season_records}
    season_names = list(season_options)
    default_season_name = next(
        (s["name"] for s in season_records if s["id"] == default_season_id),
        current_season.get("name", season_names[0]),
    )
    selected_season_name = st.selectbox(
        TEXT["season_select"],
        season_names,
        index=season_names.index(default_season_name),
    )
    season_id = season_options[selected_season_name]
    season_name = selected_season_name
    season_info = season_meta.get(season_id, {})

    teams_res = requests.get(
        f"{base_url}/teams/seasons/{season_id}",
        headers=headers,
        params=params,
        timeout=30,
    )
    teams_data = teams_res.json()
    if teams_res.status_code != 200:
        st.error(f"チーム取得エラー: {teams_res.status_code}")
        st.stop()

    st.success(TEXT["connected"])
    st.caption(f"{TEXT['season']}: {season_name}")

    teams = teams_data.get("data", [])
    team_options = {
        t.get("name", "Unknown"): t.get("id") for t in teams if t.get("id")
    }
    team_id_to_name = {v: k for k, v in team_options.items()}
    selected_team_name = st.selectbox(TEXT["team_select"], sorted(team_options))
    selected_team_id = team_options[selected_team_name]

    squad_res = requests.get(
        f"{base_url}/squads/seasons/{season_id}/teams/{selected_team_id}",
        headers=headers,
        params={
            **params,
            "include": "player.statistics.details;player.position;player.detailedPosition",
        },
        timeout=30,
    )
    squad_data = squad_res.json()
    if squad_res.status_code != 200:
        st.error(f"選手取得エラー: {squad_res.status_code}")
        st.stop()

    all_players = [
        s.get("player", {})
        for s in squad_data.get("data", [])
        if s.get("player", {}).get("name")
    ]
    minute_filter = st.selectbox(
        TEXT["minute_filter"],
        options=[900, 600, 300, 0],
        format_func=lambda v: f"{v}分以上" if v else "指定なし",
        key="legacy_min",
    )
    players = [
        p for p in all_players if minute_filter == 0 or get_minutes(p) >= minute_filter
    ]
    st.subheader(f"{selected_team_name}{TEXT['team_list']}（旧：シーズンAPI）")
    st.caption(f"対象: {len(players)} / 全{len(all_players)}")

    if players:
        player_options = {p["name"]: p["id"] for p in players if p.get("id")}
        selected_player_name = st.selectbox(
            TEXT["player_select"], sorted(player_options), key="legacy_player"
        )
        selected_player = next(
            p for p in players if p.get("id") == player_options[selected_player_name]
        )
        details = [
            d
            for s in get_season_statistics(selected_player)
            for d in s.get("details", [])
        ]
        raw_by_id = {}
        rows = []
        for d in details:
            tid = d.get("type_id")
            val = get_total_value(d)
            if tid is None:
                continue
            raw_by_id[tid] = val
            rows.append({"type_id": tid, "name": known_name(tid), "value": val})
        minutes = get_minutes(selected_player)
        position = get_position_label(selected_player)
        age = calc_age(selected_player.get("date_of_birth"))
        st.markdown(
            f"**{selected_player_name}** · {selected_team_name} · {position} · "
            f"{age or '-'}歳 · {minutes}分"
        )
        with st.expander(TEXT["all_stats"]):
            st.dataframe(
                sorted(rows, key=lambda x: x["type_id"] or 0),
                use_container_width=True,
                hide_index=True,
            )

        labels_en = [KNOWN_NAMES.get(i, (f"id{i}",))[0] for i in RADAR_ORDER_LEGACY]
        raw_values = [
            raw_by_id[i] if isinstance(raw_by_id.get(i), (int, float)) else 0
            for i in RADAR_ORDER_LEGACY
        ]
        display_values = (
            [round(v * 90 / minutes, 2) for v in raw_values]
            if minutes > 0
            else raw_values
        )
        if sum(display_values) != 0:
            fig = build_radar_figure(
                labels_en,
                display_values,
                [
                    selected_player_name,
                    f"{selected_team_name} | {position} | {minutes} min",
                    f"LEGACY season API · {season_name}",
                ],
                max(max(display_values) * 1.15, 1.0),
            )
            try:
                png = fig.to_image(format="png", width=900, height=1180, scale=2)
                st.image(png, use_container_width=True)
                st.download_button(
                    TEXT["download"],
                    data=png,
                    file_name=f"{selected_player_name}_legacy.png",
                    mime="image/png",
                    key="dl_legacy",
                )
            except Exception as ie:
                st.warning(str(ie))
        else:
            st.info(TEXT["no_stats"])

except Exception as e:
    st.error(f"接続エラー: {e}")


# ============================================================
# Phase 4: Fixture Aggregate + New Radar（並行）
# ============================================================
st.divider()
st.subheader("Fixture Aggregate Radar（新・並行実装）")
st.caption(
    "Fixture lineups.details 集計ベース。既存シーズンAPIレーダーは上に残しています。"
)


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
    if fx.get("result_info") or fx.get("scores"):
        return True
    return False


def fetch_season_fixtures(sid, season_meta_row, force_refresh=False):
    cdir = _cache_dir(sid)
    list_path = cdir / "fixtures_list.json"
    if not force_refresh:
        cached = _load_json(list_path)
        if cached and cached.get("fixtures"):
            return cached

    start = (season_meta_row.get("starting_at") or "2026-07-01")[:10]
    end = (season_meta_row.get("ending_at") or "2027-06-30")[:10]
    today = date.today().isoformat()
    if end > today:
        end = today

    all_fx = []
    page = 1
    errors = 0
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
        data = body.get("data") or []
        all_fx.extend(data)
        pag = body.get("pagination") or {}
        if not pag.get("has_more"):
            break
        page += 1
        if page > 30:
            break
        time.sleep(0.12)

    finished = [fx for fx in all_fx if _is_finished_fixture(fx)]
    payload = {
        "season_id": sid,
        "start": start,
        "end": end,
        "total_fetched": len(all_fx),
        "finished_count": len(finished),
        "list_errors": errors,
        "fixtures": [
            {
                "id": fx.get("id"),
                "name": fx.get("name"),
                "starting_at": fx.get("starting_at"),
            }
            for fx in finished
            if fx.get("id")
        ],
    }
    _save_json(list_path, payload)
    return payload


def fetch_fixture_details(sid, fixture_id, force_refresh=False):
    cdir = _cache_dir(sid)
    path = cdir / f"fixture_{fixture_id}.json"
    if not force_refresh:
        cached = _load_json(path)
        if cached is not None:
            return cached, False, None
    res = requests.get(
        f"{base_url}/fixtures/{fixture_id}",
        headers=headers,
        params={**params, "include": "lineups.details.type;participants"},
        timeout=45,
    )
    if res.status_code != 200:
        return None, True, f"HTTP {res.status_code}"
    data = (res.json() or {}).get("data")
    _save_json(path, data)
    time.sleep(0.1)
    return data, True, None


def aggregate_player_team(fixture_payloads, sid):
    """キー: season_id + player_id + team_id"""
    aggs = {}
    for fdata in fixture_payloads:
        if not fdata:
            continue
        for lu in fdata.get("lineups") or []:
            pid = lu.get("player_id")
            tid = lu.get("team_id")
            if not pid or not tid:
                continue
            key = f"{sid}_{pid}_{tid}"
            pname = (
                (lu.get("player") or {}).get("name")
                or lu.get("player_name")
                or f"id:{pid}"
            )
            pos_id = lu.get("position_id") or (
                (lu.get("player") or {}).get("position_id")
            )
            details = lu.get("details") or []

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
            for d in details:
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
                    aggs[key]["raw"][type_id] = (
                        aggs[key]["raw"].get(type_id, 0.0) + parsed
                    )
            if played:
                aggs[key]["apps"] += 1
    return aggs


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
    rank = below + (equal - 1) / 2.0
    return round(100.0 * rank / (n - 1), 1)


def compute_metrics(raw, minutes, metric_defs):
    out = {}
    for m in metric_defs:
        kind = m["kind"]
        if kind in ("per90", "lower_better_per90"):
            if minutes <= 0:
                out[m["key"]] = None
            else:
                out[m["key"]] = round(raw.get(m["tid"], 0.0) * 90.0 / minutes, 3)
        elif kind == "ratio":
            den = raw.get(m["den"], 0.0)
            num = raw.get(m["num"], 0.0)
            out[m["key"]] = round(num / den * 100.0, 2) if den > 0 else None
    return out


force = st.checkbox("キャッシュ無視で再取得", value=False, key="fx_force")
min_min = st.selectbox(
    "最低出場分（新レーダー・Percentile母集団）",
    [0, 300, 600, 900],
    index=1,
    key="fx_min",
)
run_btn = st.button("Fixture Aggregate を構築 / 更新", key="fx_run")

if "fx_aggs" not in st.session_state:
    st.session_state.fx_aggs = None
    st.session_state.fx_meta = None

if run_btn:
    try:
        with st.spinner("Fixture一覧..."):
            flist = fetch_season_fixtures(season_id, season_info, force_refresh=force)
        fx_ids = [f["id"] for f in flist.get("fixtures", [])]
        progress = st.progress(0.0)
        status = st.empty()
        loaded = []
        api_hits = cache_hits = 0
        errors = []
        for i, fid in enumerate(fx_ids):
            status.caption(f"{i+1}/{len(fx_ids)} fixture {fid}")
            data, from_api, err = fetch_fixture_details(
                season_id, fid, force_refresh=force
            )
            if err:
                errors.append({"fixture_id": fid, "error": err})
            elif data is not None:
                loaded.append(data)
                if from_api:
                    api_hits += 1
                else:
                    cache_hits += 1
            progress.progress((i + 1) / max(len(fx_ids), 1))

        aggs = aggregate_player_team(loaded, season_id)
        st.session_state.fx_aggs = aggs
        st.session_state.fx_meta = {
            "fixtures": len(loaded),
            "api_hits": api_hits,
            "cache_hits": cache_hits,
            "errors": len(errors),
            "error_rows": errors,
        }
        # 保存
        rows_out = []
        for a in aggs.values():
            rows_out.append(
                {
                    "player_id": a["player_id"],
                    "team_id": a["team_id"],
                    "player_name": a["player_name"],
                    "position_id": a["position_id"],
                    "minutes": a["minutes"],
                    "apps": a["apps"],
                    "raw": {str(k): v for k, v in a["raw"].items()},
                }
            )
        _save_json(
            _cache_dir(season_id) / "player_team_aggregate.json",
            {"season_id": season_id, "players": rows_out},
        )
        st.success(
            f"集計完了: fixtures={len(loaded)}, players={len(aggs)}, "
            f"api={api_hits}, cache={cache_hits}, err={len(errors)}"
        )
    except Exception as e:
        st.error(f"Aggregate error: {e}")

# キャッシュから復元試行
if st.session_state.fx_aggs is None:
    cached_agg = _load_json(_cache_dir(season_id) / "player_team_aggregate.json")
    if cached_agg and cached_agg.get("players"):
        restored = {}
        for p in cached_agg["players"]:
            key = f"{season_id}_{p['player_id']}_{p['team_id']}"
            restored[key] = {
                "season_id": season_id,
                "player_id": p["player_id"],
                "team_id": p["team_id"],
                "player_name": p["player_name"],
                "position_id": p.get("position_id"),
                "minutes": float(p.get("minutes") or 0),
                "apps": p.get("apps") or 0,
                "raw": {int(k): v for k, v in (p.get("raw") or {}).items()},
            }
        st.session_state.fx_aggs = restored
        st.caption("player_team_aggregate.json から復元しました")

aggs = st.session_state.fx_aggs
if not aggs:
    st.info("上のボタンで Fixture Aggregate を構築してください。")
else:
    # Raw確認表
    table = []
    for a in aggs.values():
        mins = a["minutes"]
        if mins < float(min_min):
            continue
        raw = a["raw"]
        pos = POSITION_MAP.get(a["position_id"], a["position_id"])
        passes = raw.get(80, 0.0)
        acc = raw.get(116, 0.0)
        table.append(
            {
                "Player": a["player_name"],
                "Team": team_id_to_name.get(a["team_id"], a["team_id"]),
                "Pos": pos,
                "Minutes": int(round(mins)),
                "Apps": a["apps"],
                "Goals": int(raw.get(52, 0)),
                "Assists": int(raw.get(79, 0)),
                "Passes": int(passes),
                "Accurate Passes": int(acc),
                "Pass Acc %": round(acc / passes * 100, 1) if passes > 0 else None,
            }
        )
    table.sort(key=lambda r: r["Minutes"], reverse=True)

    st.markdown("#### Raw確認（Goals / Assists 含む）")
    st.caption(f"最低出場 {min_min}分 · {len(table)}人 · Key = season_id + player_id + team_id")
    st.dataframe(table[:60], use_container_width=True, hide_index=True)

    # Percentile母集団
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
                "key": f"{a['player_id']}_{a['team_id']}",
                "player_id": a["player_id"],
                "team_id": a["team_id"],
                "Player": a["player_name"],
                "Team": team_id_to_name.get(a["team_id"], a["team_id"]),
                "Pos": pos,
                "Minutes": int(round(mins)),
                "metrics": metrics,
                "raw": a["raw"],
            }
        )

    for pos, group in by_pos.items():
        for m in POSITION_METRICS[pos]:
            vals = [
                g["metrics"][m["key"]]
                for g in group
                if g["metrics"].get(m["key"]) is not None
            ]
            higher = m["kind"] != "lower_better_per90"
            for g in group:
                v = g["metrics"].get(m["key"])
                if v is None:
                    g.setdefault("pct", {})[m["key"]] = None
                else:
                    g.setdefault("pct", {})[m["key"]] = percentile_rank(
                        vals, v, higher_is_better=higher
                    )

    st.markdown("#### Percentile母集団（選択した最低出場以上）")
    st.write({p: len(by_pos[p]) for p in by_pos})

    # 選手選択 → 新レーダー
    all_opts = []
    for pos in ("GK", "DEF", "MID", "FWD"):
        for g in by_pos[pos]:
            all_opts.append(
                (
                    f"{g['Player']} | {g['Team']} | {pos} | {g['Minutes']}min",
                    g,
                )
            )
    all_opts.sort(key=lambda x: x[0])
    if not all_opts:
        st.warning("表示対象選手がいません。最低出場分を下げてください。")
    else:
        labels_list = [o[0] for o in all_opts]
        choice = st.selectbox("新レーダー選手", labels_list, key="fx_player")
        selected = next(g for lab, g in all_opts if lab == choice)
        pos = selected["Pos"]
        mdefs = POSITION_METRICS[pos]

        st.markdown(
            f"**{selected['Player']}** · {selected['Team']} · {pos} · "
            f"{selected['Minutes']}分"
        )

        # 確認表
        check_rows = []
        radar_labels = []
        radar_values = []
        for m in mdefs:
            raw_v = None
            if m["kind"] in ("per90", "lower_better_per90"):
                raw_v = selected["raw"].get(m["tid"], 0)
            elif m["kind"] == "ratio":
                raw_v = f"{selected['raw'].get(m['num'], 0)} / {selected['raw'].get(m['den'], 0)}"
            check_rows.append(
                {
                    "Metric": m["label"],
                    "Raw": raw_v,
                    "Per90 / %": selected["metrics"].get(m["key"]),
                    "Percentile": selected.get("pct", {}).get(m["key"]),
                    "向き": "低いほど良"
                    if m["kind"] == "lower_better_per90"
                    else "高いほど良",
                }
            )
            # レーダー軸は Percentile（0-100）で描画
            pct = selected.get("pct", {}).get(m["key"])
            radar_labels.append(m["label"])
            radar_values.append(pct if pct is not None else 0)

        st.markdown("#### Metric確認表")
        st.dataframe(check_rows, use_container_width=True, hide_index=True)

        if any(v > 0 for v in radar_values):
            fig2 = build_radar_figure(
                radar_labels,
                radar_values,
                [
                    selected["Player"],
                    f"{selected['Team']} | {pos} | {selected['Minutes']} min",
                    f"Fixture Aggregate · Percentile · {season_name}",
                ],
                100,
            )
            try:
                png2 = fig2.to_image(format="png", width=900, height=1180, scale=2)
                st.image(png2, use_container_width=True)
                st.caption("軸は同ポジション内 Percentile（0–100）。Conc./Fouls は反転済み。")
                st.download_button(
                    "新レーダー PNG",
                    data=png2,
                    file_name=f"{selected['Player']}_fixture_radar.png",
                    mime="image/png",
                    key="dl_new",
                )
            except Exception as ie:
                st.warning(str(ie))
        else:
            st.info("Percentileがすべて空です。")
