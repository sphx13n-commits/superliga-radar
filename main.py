import base64
import os
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
CARD_BORDER = "#D0DAE6"

# 実測: Fixture details の出場時間
MINUTES_TYPE_ID = 117172

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
    "no_team": "No teams found" if is_english else "チームが見つかりません",
    "team_list": " squad" if is_english else "の選手一覧",
    "save_hint": "Long-press to save." if is_english else "長押しで保存できます。",
    "download": "Download PNG" if is_english else "PNGをダウンロード",
    "no_players": "No players" if is_english else "選手データがありません",
    "no_stats": "No stats" if is_english else "この選手のスタッツがありません",
    "all_stats": "Season API stats" if is_english else "シーズンAPIの指標",
    "per90_note": "Per 90." if is_english else "90分あたり。",
    "description": "Superliga radar" if is_english else "スーペルリーガの選手レーダー",
}

st.markdown(
    """
    <style>
      .block-container { padding-top: 0.8rem; padding-bottom: 1.2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)
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
    42: ("Shots total", "シュート合計"),
    52: ("Goals", "ゴール"),
    78: ("Tackles", "タックル"),
    79: ("Assists", "アシスト"),
    80: ("Passes", "パス"),
    86: ("Shots on target", "枠内シュート"),
    100: ("Interceptions", "インターセプト"),
    101: ("Clearances", "クリア"),
    107: ("Aerials won", "空中戦勝利"),
    109: ("Successful dribbles", "ドリブル成功"),
    116: ("Accurate passes", "成功パス"),
    117: ("Key passes", "キーパス"),
    119: ("Minutes (season)", "出場時間(シーズン)"),
    MINUTES_TYPE_ID: ("Minutes (fixture)", "出場時間(試合)"),
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
    pid = player.get("position_id")
    return POSITION_MAP.get(pid, "MID")


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


try:
    league_res = requests.get(
        f"{base_url}/leagues/271",
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
# Aggregate Prototype v2
# 同一チーム（AGF優先）の複数試合で合算検証
# ============================================================
st.divider()
st.subheader("Aggregate Prototype v2（複数試合合算の検証）")
st.caption(
    "同一チームの終了試合を最大5試合取得し、同じ player_id の合算を検証します。"
)

_proto_token = os.getenv("SPORTMONKS_TOKEN")
if _proto_token:
    _base = "https://api.sportmonks.com/v3/football"
    _headers = {"Authorization": _proto_token}
    _params = {"api_token": _proto_token}
    _POS = {24: "GK", 25: "DEF", 26: "MID", 27: "FWD"}

    # 主要指標
    TRACK_IDS = {
        52: "Goals",
        42: "Shots",
        80: "Passes",
        116: "Accurate Passes",
        117: "Key Passes",
        78: "Tackles",
        100: "Interceptions",
        101: "Clearances",
        107: "Aerials Won",
        109: "Succ. Dribbles",
    }

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
            for k in (
                "total",
                "minutes",
                "minute",
                "value",
                "average",
                "count",
                "sum",
                "percentage",
            ):
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

    c1, c2, c3 = st.columns(3)
    with c1:
        start_d = st.text_input("開始日", value="2026-07-20", key="proto_start")
    with c2:
        end_d = st.text_input("終了日", value="2026-08-20", key="proto_end")
    with c3:
        max_fx = st.number_input(
            "最大試合数", min_value=2, max_value=5, value=5, key="proto_max"
        )

    focus_team = st.text_input(
        "優先チーム名（部分一致）",
        value="AGF",
        key="proto_team",
        help="この名前を含む試合を優先して選びます",
    )

    if st.button("同一チームの複数試合を集計する", key="proto_run"):
        try:
            between_res = requests.get(
                f"{_base}/fixtures/between/{start_d}/{end_d}",
                headers=_headers,
                params={
                    **_params,
                    "filters": "fixtureLeagues:271",
                    "include": "participants",
                },
                timeout=40,
            )
            between_json = between_res.json()
            if between_res.status_code != 200:
                st.error(f"between 失敗: {between_res.status_code}")
            else:
                all_fx = between_json.get("data") or []
                focus = (focus_team or "").strip().lower()

                def involves_focus(fx):
                    name = (fx.get("name") or "").lower()
                    if focus and focus in name:
                        return True
                    for p in fx.get("participants") or []:
                        pn = (p.get("name") or "").lower()
                        if focus and focus in pn:
                            return True
                    return False

                focused = [fx for fx in all_fx if involves_focus(fx)]
                # 日付順
                focused.sort(key=lambda x: x.get("starting_at") or "")
                others = [fx for fx in all_fx if fx not in focused]
                others.sort(key=lambda x: x.get("starting_at") or "")

                selected = focused[: int(max_fx)]
                if len(selected) < int(max_fx):
                    selected += others[: int(max_fx) - len(selected)]

                st.write(
                    f"期間内ヒット: {len(all_fx)} / "
                    f"『{focus_team}』関連: {len(focused)} / "
                    f"使用: {len(selected)}"
                )
                if len(focused) < 2:
                    st.warning(
                        f"『{focus_team}』の試合が2未満です。"
                        "開始日を広げると複数試合合算を検証しやすくなります。"
                    )

                if not selected:
                    st.warning("試合がありません。")
                else:
                    fixture_rows = []
                    # player_id -> agg
                    # per_fixture: list of {fixture_id, match, minutes, stats..., lineup_type}
                    aggs = {}
                    minutes_type_codes = {}  # type_id -> code（分関連の探索）

                    for fx in selected:
                        fid = fx.get("id")
                        fname = fx.get("name") or str(fid)
                        fdate = (fx.get("starting_at") or "")[:10]
                        fixture_rows.append(
                            {"fixture_id": fid, "match": fname, "date": fdate}
                        )

                        fr = requests.get(
                            f"{_base}/fixtures/{fid}",
                            headers=_headers,
                            params={**_params, "include": "lineups.details.type"},
                            timeout=40,
                        )
                        if fr.status_code != 200:
                            st.warning(f"{fid} 失敗: {fr.status_code}")
                            continue

                        lineups = (
                            ((fr.json() or {}).get("data") or {}).get("lineups") or []
                        )
                        st.caption(
                            f"fixture {fid}: lineups={len(lineups)} / {fname}"
                        )

                        for lu in lineups:
                            pid = lu.get("player_id")
                            if not pid:
                                continue
                            pname = (
                                (lu.get("player") or {}).get("name")
                                or lu.get("player_name")
                                or f"id:{pid}"
                            )
                            pos_id = lu.get("position_id") or (
                                (lu.get("player") or {}).get("position_id")
                            )
                            # 11=先発, 12=ベンチ が多い
                            lineup_type = lu.get("type_id")
                            details = lu.get("details") or []

                            if pid not in aggs:
                                aggs[pid] = {
                                    "player_id": pid,
                                    "player_name": pname,
                                    "position_id": pos_id,
                                    "minutes": 0.0,
                                    "raw": {},
                                    "fixture_count": 0,
                                    "per_fixture": [],
                                }
                            else:
                                if pname and str(aggs[pid]["player_name"]).startswith(
                                    "id:"
                                ):
                                    aggs[pid]["player_name"] = pname
                                if pos_id and not aggs[pid]["position_id"]:
                                    aggs[pid]["position_id"] = pos_id

                            fx_stats = {tid: 0.0 for tid in TRACK_IDS}
                            fx_minutes = 0.0

                            for d in details:
                                tid = d.get("type_id")
                                if tid is None:
                                    continue
                                t = d.get("type") or {}
                                code = (t.get("code") or "").lower()
                                name = (t.get("name") or "").lower()
                                # 分関連 type を記録
                                if (
                                    "minute" in code
                                    or "minute" in name
                                    or tid in (119, MINUTES_TYPE_ID, 321, 322)
                                ):
                                    minutes_type_codes[tid] = (
                                        t.get("code") or t.get("name") or str(tid)
                                    )

                                parsed = _extract_stat(d)
                                if parsed is None:
                                    continue
                                if tid == MINUTES_TYPE_ID:
                                    fx_minutes += parsed
                                elif tid in TRACK_IDS:
                                    fx_stats[tid] = fx_stats.get(tid, 0.0) + parsed
                                # 合算用 raw（全type）
                                if tid != MINUTES_TYPE_ID:
                                    aggs[pid]["raw"][tid] = (
                                        aggs[pid]["raw"].get(tid, 0.0) + parsed
                                    )

                            # 出場があった／スタッツがある選手のみ fixture カウント
                            if fx_minutes > 0 or any(v > 0 for v in fx_stats.values()):
                                aggs[pid]["fixture_count"] += 1
                                aggs[pid]["minutes"] += fx_minutes
                                aggs[pid]["per_fixture"].append(
                                    {
                                        "fixture_id": fid,
                                        "match": fname,
                                        "date": fdate,
                                        "minutes_117172": fx_minutes,
                                        "lineup_type_id": lineup_type,
                                        "lineup_role": (
                                            "start"
                                            if lineup_type == 11
                                            else "bench"
                                            if lineup_type == 12
                                            else str(lineup_type)
                                        ),
                                        **{
                                            TRACK_IDS[tid]: fx_stats.get(tid, 0.0)
                                            for tid in TRACK_IDS
                                        },
                                    }
                                )

                    # ① Fixture一覧
                    st.markdown("#### ① 使用Fixture一覧")
                    st.dataframe(
                        fixture_rows, use_container_width=True, hide_index=True
                    )

                    # ② lineups数は caption 済み

                    # ③ 複数Fixture選手
                    multi = [
                        a for a in aggs.values() if len(a["per_fixture"]) >= 2
                    ]
                    multi.sort(
                        key=lambda a: len(a["per_fixture"]), reverse=True
                    )
                    st.markdown(
                        f"#### ③ 複数Fixtureに出場した選手数: **{len(multi)}**"
                    )

                    # Minutes関連 type 一覧
                    st.markdown("#### Minutes関連 type_id（この取得分で出現）")
                    if minutes_type_codes:
                        st.write(
                            [
                                {"type_id": k, "code": v}
                                for k, v in sorted(minutes_type_codes.items())
                            ]
                        )
                    else:
                        st.write("分関連 type が検出できませんでした")

                    if not multi:
                        st.error(
                            "複数試合出場選手が0人です。"
                            "日付範囲を広げるか、優先チーム名を確認してください。"
                        )
                    else:
                        st.markdown("#### ④ Aggregate検証対象（複数試合選手）")
                        summary_rows = []
                        for a in multi[:15]:
                            summary_rows.append(
                                {
                                    "Player": a["player_name"],
                                    "player_id": a["player_id"],
                                    "Pos": _POS.get(
                                        a["position_id"], a["position_id"]
                                    ),
                                    "Fixture数": len(a["per_fixture"]),
                                    "Minutes合計(117172)": int(
                                        round(a["minutes"])
                                    ),
                                    "各試合Minutes": " + ".join(
                                        str(int(round(p["minutes_117172"])))
                                        for p in a["per_fixture"]
                                    ),
                                }
                            )
                        st.dataframe(
                            summary_rows,
                            use_container_width=True,
                            hide_index=True,
                        )

                        # 上位3人を詳細検証
                        st.markdown(
                            "#### 詳細検証（複数試合選手 最大5人）"
                        )
                        for a in multi[:5]:
                            st.markdown(
                                f"**{a['player_name']}** "
                                f"(player_id={a['player_id']}, "
                                f"fixtures={len(a['per_fixture'])})"
                            )
                            # Fixtureごと
                            fx_table = []
                            manual_sum = {TRACK_IDS[t]: 0.0 for t in TRACK_IDS}
                            manual_min = 0.0
                            for p in a["per_fixture"]:
                                row = {
                                    "fixture_id": p["fixture_id"],
                                    "match": p["match"],
                                    "role": p["lineup_role"],
                                    "Minutes_117172": p["minutes_117172"],
                                }
                                for tid, label in TRACK_IDS.items():
                                    row[label] = p.get(label, 0.0)
                                    manual_sum[label] += p.get(label, 0.0)
                                manual_min += p["minutes_117172"]
                                fx_table.append(row)
                            st.dataframe(
                                fx_table,
                                use_container_width=True,
                                hide_index=True,
                            )

                            # Aggregate との一致
                            raw = a["raw"]
                            agg_check = {
                                "Minutes合計_117172": round(a["minutes"], 2),
                                "手動Minutes合計": round(manual_min, 2),
                                "一致_Minutes": abs(a["minutes"] - manual_min)
                                < 0.01,
                            }
                            for tid, label in TRACK_IDS.items():
                                agg_v = raw.get(tid, 0.0)
                                man_v = manual_sum[label]
                                agg_check[f"Agg_{label}"] = agg_v
                                agg_check[f"手動_{label}"] = man_v
                                agg_check[f"一致_{label}"] = (
                                    abs(agg_v - man_v) < 0.01
                                )

                            mins = a["minutes"]
                            passes = raw.get(80, 0.0)
                            acc = raw.get(116, 0.0)
                            pass_pct = (
                                round(acc / passes * 100.0, 2)
                                if passes > 0
                                else None
                            )
                            per90_goals = (
                                round(raw.get(52, 0.0) * 90 / mins, 2)
                                if mins > 0
                                else None
                            )
                            per90_passes = (
                                round(passes * 90 / mins, 2)
                                if mins > 0
                                else None
                            )

                            st.write(
                                {
                                    **agg_check,
                                    "Pass Acc % (Σ116/Σ80)": pass_pct,
                                    "Goals/90": per90_goals,
                                    "Passes/90": per90_passes,
                                }
                            )
                            st.caption(
                                "117172 の各試合値と合計を確認。"
                                "通常リーグ戦で90超が出る場合は、"
                                "プレー時間以外（累計等）の可能性があるため要注記。"
                            )

                        # 全体 Aggregate 表（Minutes>0）
                        sample = []
                        for a in aggs.values():
                            if a["minutes"] <= 0 and not a["per_fixture"]:
                                continue
                            mins = a["minutes"]
                            raw = a["raw"]

                            def p90(tid):
                                if mins <= 0:
                                    return None
                                return round(
                                    raw.get(tid, 0.0) * 90.0 / mins, 2
                                )

                            passes = raw.get(80, 0.0)
                            acc = raw.get(116, 0.0)
                            sample.append(
                                {
                                    "Player": a["player_name"],
                                    "player_id": a["player_id"],
                                    "Pos": _POS.get(
                                        a["position_id"], a["position_id"]
                                    ),
                                    "Fixtures": len(a["per_fixture"]),
                                    "Minutes": int(round(mins)),
                                    "Goals/90": p90(52),
                                    "Shots/90": p90(42),
                                    "Passes/90": p90(80),
                                    "Pass Acc %": (
                                        round(acc / passes * 100.0, 1)
                                        if passes > 0
                                        else None
                                    ),
                                    "Key Passes/90": p90(117),
                                    "Tackles/90": p90(78),
                                    "Intercepts/90": p90(100),
                                }
                            )
                        sample.sort(
                            key=lambda x: (x["Fixtures"], x["Minutes"]),
                            reverse=True,
                        )
                        st.markdown("#### 全体 Aggregate（Fixtures多い順）")
                        st.dataframe(
                            sample[:30],
                            use_container_width=True,
                            hide_index=True,
                        )

        except Exception as e:
            st.error(f"Prototype エラー: {e}")
