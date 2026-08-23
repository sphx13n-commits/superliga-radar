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
    "season": "Season" if is_english else "シーズン",
    "season_select": "Select a season" if is_english else "シーズンを選択",
    "team_select": "Select a team" if is_english else "チームを選択",
    "player_select": "Select a player" if is_english else "選手を選択",
    "minute_filter": "Minutes filter" if is_english else "出場時間",
    "team_list": " squad" if is_english else "の選手一覧",
    "download": "Download PNG" if is_english else "PNGをダウンロード",
    "no_stats": "No stats" if is_english else "この選手のスタッツがありません",
    "all_stats": "Season API stats" if is_english else "シーズンAPIの指標",
    "description": "Superliga radar" if is_english else "スーペルリーガの選手レーダー",
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
    42: ("Shots total", "シュート"),
    52: ("Goals", "ゴール"),
    78: ("Tackles", "タックル"),
    79: ("Assists", "アシスト"),
    80: ("Passes", "パス"),
    100: ("Interceptions", "インターセプト"),
    101: ("Clearances", "クリア"),
    107: ("Aerials won", "空中戦"),
    109: ("Successful dribbles", "ドリブル成功"),
    119: ("Minutes", "出場時間"),
    194: ("Clean sheets", "無失点"),
    214: ("Team wins", "勝利"),
    215: ("Team draws", "引き分け"),
    216: ("Team losses", "敗戦"),
    321: ("Appearances", "出場数"),
    322: ("Lineups", "先発数"),
}
RADAR_ORDER = [52, 79, 42, 78, 100, 101, 107, 109]
POSITION_MAP = {24: "GK", 25: "DEF", 26: "MID", 27: "FWD"}


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
    fig.update_layout(
        height=820,
        margin={"l": 36, "r": 36, "t": 140, "b": 78},
        paper_bgcolor=WHITE,
        plot_bgcolor=WHITE,
        showlegend=False,
        images=[
            {
                "source": get_logo_data_uri(),
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
        ],
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
                "tickfont": {"color": NAVY, "size": 16},
                "rotation": 90,
                "direction": "clockwise",
            },
        },
    )
    return fig


# ========== 既存：シーズンAPIレーダー（変更なし） ==========
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
    )
    players = [
        p for p in all_players if minute_filter == 0 or get_minutes(p) >= minute_filter
    ]
    st.subheader(f"{selected_team_name}{TEXT['team_list']}")
    st.caption(f"対象: {len(players)} / 全{len(all_players)}")

    if players:
        player_options = {p["name"]: p["id"] for p in players if p.get("id")}
        selected_player_name = st.selectbox(
            TEXT["player_select"], sorted(player_options)
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

        labels_en = [KNOWN_NAMES.get(i, (f"id{i}",))[0] for i in RADAR_ORDER]
        raw_values = [
            raw_by_id[i] if isinstance(raw_by_id.get(i), (int, float)) else 0
            for i in RADAR_ORDER
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
                    f"Superliga {season_name} · season API",
                ],
                max(max(display_values) * 1.15, 1.0),
            )
            try:
                png = fig.to_image(format="png", width=900, height=1180, scale=2)
                st.image(png, use_container_width=True)
                st.download_button(
                    TEXT["download"],
                    data=png,
                    file_name=f"{selected_player_name}_radar.png",
                    mime="image/png",
                )
            except Exception as ie:
                st.warning(str(ie))
        else:
            st.info(TEXT["no_stats"])

except Exception as e:
    st.error(f"接続エラー: {e}")


# ============================================================
# Fixture Season Aggregate（Phase 2）
# キャッシュ付き・既存レーダーは非接触
# ============================================================
st.divider()
st.subheader("Fixture Season Aggregate（Phase 2）")
st.caption(
    "終了済み Superliga 全Fixture → キャッシュ → 選手シーズン合算。"
    "既存レーダーは変更していません。"
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
    """終了試合判定（延長なしのリーグ戦想定）"""
    state = fx.get("state") or {}
    state_id = fx.get("state_id") or state.get("id")
    # Sportmonks: 5=FT が多い。名称でも判定
    name = (state.get("short_name") or state.get("name") or state.get("developer_name") or "").upper()
    if state_id in (5, 7, 8):  # FT / AET / FT_PEN など
        return True
    if name in ("FT", "FULL TIME", "FINISHED", "AET", "FT_PEN"):
        return True
    # result_info や scores がある場合も終了扱い
    if fx.get("result_info"):
        return True
    scores = fx.get("scores") or []
    if scores:
        return True
    return False


def fetch_season_fixtures(sid, season_meta_row, force_refresh=False):
    """シーズンのFixture一覧（ページネーション対応）+ キャッシュ"""
    cdir = _cache_dir(sid)
    list_path = cdir / "fixtures_list.json"
    if not force_refresh:
        cached = _load_json(list_path)
        if cached and cached.get("fixtures"):
            return cached

    start = (season_meta_row.get("starting_at") or "2026-07-01")[:10]
    end = (season_meta_row.get("ending_at") or "2027-06-30")[:10]
    # 進行中シーズンは今日まで
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
        time.sleep(0.15)

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
                "state_id": fx.get("state_id"),
            }
            for fx in finished
            if fx.get("id")
        ],
    }
    _save_json(list_path, payload)
    return payload


def fetch_fixture_details(sid, fixture_id, force_refresh=False):
    """1試合の lineups.details を取得（ファイルキャッシュ）"""
    cdir = _cache_dir(sid)
    path = cdir / f"fixture_{fixture_id}.json"
    if not force_refresh:
        cached = _load_json(path)
        if cached is not None:
            return cached, False, None  # data, from_api, error

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
    time.sleep(0.12)
    return data, True, None


def aggregate_from_fixtures(fixture_payloads):
    """fixtures の lineups から PlayerSeasonAggregate を作る"""
    aggs = {}
    for fdata in fixture_payloads:
        if not fdata:
            continue
        lineups = fdata.get("lineups") or []
        for lu in lineups:
            pid = lu.get("player_id")
            if not pid:
                continue
            pname = (
                (lu.get("player") or {}).get("name")
                or lu.get("player_name")
                or f"id:{pid}"
            )
            team_id = lu.get("team_id")
            pos_id = lu.get("position_id") or (
                (lu.get("player") or {}).get("position_id")
            )
            details = lu.get("details") or []

            if pid not in aggs:
                aggs[pid] = {
                    "player_id": pid,
                    "player_name": pname,
                    "team_id": team_id,
                    "position_id": pos_id,
                    "minutes": 0.0,
                    "raw": {},
                    "fixture_appearances": 0,
                }
            else:
                if pname and str(aggs[pid]["player_name"]).startswith("id:"):
                    aggs[pid]["player_name"] = pname
                if pos_id and not aggs[pid]["position_id"]:
                    aggs[pid]["position_id"] = pos_id
                # 複数チームは最後の team_id を保持（簡易）
                if team_id:
                    aggs[pid]["team_id"] = team_id

            played = False
            for d in details:
                tid = d.get("type_id")
                if tid is None:
                    continue
                parsed = _extract_stat(d)
                if parsed is None:
                    continue
                if tid == MINUTES_TYPE_ID:
                    aggs[pid]["minutes"] += parsed
                    if parsed > 0:
                        played = True
                else:
                    aggs[pid]["raw"][tid] = aggs[pid]["raw"].get(tid, 0.0) + parsed
            if played:
                aggs[pid]["fixture_appearances"] += 1
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


# UI
force = st.checkbox("キャッシュを無視して再取得（API消費大）", value=False)
min_min = st.selectbox("最低出場分（表示用）", [0, 300, 600, 900], index=3)
run_agg = st.button("シーズンAggregateを構築 / 更新", key="agg_run")

if run_agg:
    try:
        with st.spinner("Fixture一覧を取得中..."):
            flist = fetch_season_fixtures(season_id, season_info, force_refresh=force)

        fx_ids = [f["id"] for f in flist.get("fixtures", [])]
        st.markdown("#### A. Fixture取得")
        st.write(
            {
                "season_id": season_id,
                "season": season_name,
                "期間": f"{flist.get('start')} ~ {flist.get('end')}",
                "一覧で取得した総数": flist.get("total_fetched"),
                "終了済みと判定": flist.get("finished_count"),
                "集計対象 fixture_id 数": len(fx_ids),
                "一覧APIエラー": flist.get("list_errors"),
                "force_refresh": force,
            }
        )

        progress = st.progress(0.0)
        status = st.empty()
        loaded = []
        api_hits = 0
        cache_hits = 0
        errors = []

        for i, fid in enumerate(fx_ids):
            status.caption(f"Fixture {i+1}/{len(fx_ids)} id={fid}")
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

        status.caption("集計中...")
        aggs = aggregate_from_fixtures(loaded)

        # 表データ
        rows = []
        for a in aggs.values():
            mins = a["minutes"]
            raw = a["raw"]
            pos = POSITION_MAP.get(a["position_id"], a["position_id"])

            def p90(tid):
                if mins <= 0:
                    return None
                return round(raw.get(tid, 0.0) * 90.0 / mins, 2)

            passes = raw.get(80, 0.0)
            acc = raw.get(116, 0.0)
            pass_pct = round(acc / passes * 100.0, 1) if passes > 0 else None
            rows.append(
                {
                    "Player": a["player_name"],
                    "player_id": a["player_id"],
                    "Team": team_id_to_name.get(a["team_id"], a["team_id"]),
                    "Pos": pos,
                    "position_id": a["position_id"],
                    "Minutes": int(round(mins)),
                    "Apps": a["fixture_appearances"],
                    "Goals/90": p90(52),
                    "Assists/90": p90(79),
                    "Shots/90": p90(42),
                    "Passes/90": p90(80),
                    "Pass Acc %": pass_pct,
                    "Key Passes/90": p90(117),
                    "Tackles/90": p90(78),
                    "Intercepts/90": p90(100),
                    "Clearances/90": p90(101),
                    "Aerials/90": p90(107),
                    "Succ. Dribbles/90": p90(109),
                }
            )

        rows.sort(key=lambda r: r["Minutes"], reverse=True)
        filtered = [r for r in rows if r["Minutes"] >= min_min]

        # Percentile（同一Pos、デフォルト表示は min_min 以上）
        for pos in ("GK", "DEF", "MID", "FWD"):
            group = [r for r in filtered if r["Pos"] == pos]
            metric_keys = [
                "Goals/90",
                "Assists/90",
                "Passes/90",
                "Pass Acc %",
                "Key Passes/90",
                "Tackles/90",
                "Intercepts/90",
                "Clearances/90",
                "Aerials/90",
            ]
            for mk in metric_keys:
                vals = [g[mk] for g in group if g.get(mk) is not None]
                for g in group:
                    v = g.get(mk)
                    if v is None or not vals:
                        g[f"pct_{mk}"] = None
                    else:
                        g[f"pct_{mk}"] = percentile_rank(vals, v, True)

        st.markdown("#### B. 集計")
        with_mins = [r for r in rows if r["Minutes"] > 0]
        counts = {p: 0 for p in ("GK", "DEF", "MID", "FWD")}
        for r in with_mins:
            if r["Pos"] in counts:
                counts[r["Pos"]] += 1
        st.write(
            {
                "実際に読み込めたFixture": len(loaded),
                "API新規取得": api_hits,
                "キャッシュヒット": cache_hits,
                "Fixtureエラー数": len(errors),
                "集計選手数": len(rows),
                "Minutes>0": len(with_mins),
                f"Minutes>={min_min}": len(filtered),
                "ポジション別(Minutes>0)": counts,
            }
        )
        if errors:
            st.warning("エラーFixture")
            st.dataframe(errors, use_container_width=True, hide_index=True)

        st.markdown("#### 選手集計表（Minutes降順）")
        st.dataframe(filtered[:80], use_container_width=True, hide_index=True)

        # C. サンプル
        st.markdown("#### C. サンプル検証（各ポジション1名）")
        for pos in ("GK", "DEF", "MID", "FWD"):
            cand = [r for r in filtered if r["Pos"] == pos]
            if not cand:
                st.caption(f"{pos}: 該当なし")
                continue
            s = cand[0]
            st.markdown(
                f"**{pos}: {s['Player']}**（{s['Team']}, {s['Minutes']}分）"
            )
            st.write(
                {
                    "Minutes": s["Minutes"],
                    "Passes/90": s["Passes/90"],
                    "Pass Acc %": s["Pass Acc %"],
                    "Tackles/90": s["Tackles/90"],
                    "Goals/90": s["Goals/90"],
                    "pct_Passes/90": s.get("pct_Passes/90"),
                    "pct_Tackles/90": s.get("pct_Tackles/90"),
                }
            )

        # 集計結果もキャッシュ
        agg_path = _cache_dir(season_id) / "player_season_aggregate.json"
        _save_json(
            agg_path,
            {
                "season_id": season_id,
                "built_at": datetime.utcnow().isoformat() + "Z",
                "players": rows,
            },
        )
        st.success(
            f"集計完了。キャッシュ: cache/superliga/season_{season_id}/ "
            f"（fixtures_list + fixture_*.json + player_season_aggregate.json）"
        )
        st.caption(
            "次回はキャッシュから読むため、APIはほぼ増えません。"
            "再取得したいときだけ「キャッシュを無視」にチェック。"
        )

    except Exception as e:
        st.error(f"Aggregate エラー: {e}")
