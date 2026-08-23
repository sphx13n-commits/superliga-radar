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

MINUTES_119 = 119
MINUTES_117172 = 117172

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
    119: ("Minutes (season)", "出場時間"),
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
# Minutes 比較: type_id 119 vs 117172 のみ
# ============================================================
st.divider()
st.subheader("Minutes比較: 119 vs 117172（一時）")
st.caption(
    "同一Fixture内で minutes-played(119) と cumulative-minutes-played(117172) を並べます。"
)

_proto_token = os.getenv("SPORTMONKS_TOKEN")
if _proto_token:
    _base = "https://api.sportmonks.com/v3/football"
    _headers = {"Authorization": _proto_token}
    _params = {"api_token": _proto_token}

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
        start_d = st.text_input("開始日", value="2026-07-20", key="mc_start")
    with c2:
        end_d = st.text_input("終了日", value="2026-08-20", key="mc_end")
    with c3:
        max_fx = st.number_input("最大試合数", min_value=1, max_value=5, value=3, key="mc_max")

    focus_team = st.text_input("優先チーム", value="AGF", key="mc_team")

    if st.button("Minutes比較を実行", key="mc_run"):
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
            if between_res.status_code != 200:
                st.error(f"between 失敗: {between_res.status_code}")
            else:
                all_fx = between_res.json().get("data") or []
                focus = (focus_team or "").strip().lower()

                def involves(fx):
                    name = (fx.get("name") or "").lower()
                    if focus and focus in name:
                        return True
                    for p in fx.get("participants") or []:
                        if focus and focus in (p.get("name") or "").lower():
                            return True
                    return False

                focused = [fx for fx in all_fx if involves(fx)]
                focused.sort(key=lambda x: x.get("starting_at") or "")
                selected = focused[: int(max_fx)]
                if not selected:
                    selected = all_fx[: int(max_fx)]

                st.write(f"使用Fixture数: {len(selected)}")
                rows = []
                meta_119 = None
                meta_117172 = None
                count_119_present = 0
                count_119_nonnull = 0
                count_117172_nonnull = 0
                equal_count = 0
                compare_count = 0

                for fx in selected:
                    fid = fx.get("id")
                    fname = fx.get("name") or str(fid)
                    fdate = (fx.get("starting_at") or "")[:10]

                    fr = requests.get(
                        f"{_base}/fixtures/{fid}",
                        headers=_headers,
                        params={**_params, "include": "lineups.details.type"},
                        timeout=40,
                    )
                    if fr.status_code != 200:
                        st.warning(f"{fid} 失敗: {fr.status_code}")
                        continue

                    lineups = ((fr.json() or {}).get("data") or {}).get("lineups") or []
                    st.caption(f"{fid}: lineups={len(lineups)} / {fname}")

                    for lu in lineups:
                        pid = lu.get("player_id")
                        if not pid:
                            continue
                        pname = (
                            (lu.get("player") or {}).get("name")
                            or lu.get("player_name")
                            or f"id:{pid}"
                        )
                        lineup_type = lu.get("type_id")  # 11 start, 12 bench
                        role = (
                            "start"
                            if lineup_type == 11
                            else "bench"
                            if lineup_type == 12
                            else str(lineup_type)
                        )
                        details = lu.get("details") or []

                        v119 = None
                        v117172 = None
                        present_119 = False
                        present_117172 = False
                        raw_119 = None
                        raw_117172 = None

                        for d in details:
                            tid = d.get("type_id")
                            t = d.get("type") or {}
                            if tid == MINUTES_119:
                                present_119 = True
                                count_119_present += 1
                                raw_119 = d.get("data")
                                v119 = _extract_stat(d)
                                if meta_119 is None:
                                    meta_119 = {
                                        "type_id": tid,
                                        "code": t.get("code"),
                                        "name": t.get("name"),
                                        "developer_name": t.get("developer_name"),
                                        "data_sample": d.get("data"),
                                    }
                                if v119 is not None:
                                    count_119_nonnull += 1
                            elif tid == MINUTES_117172:
                                present_117172 = True
                                raw_117172 = d.get("data")
                                v117172 = _extract_stat(d)
                                if meta_117172 is None:
                                    meta_117172 = {
                                        "type_id": tid,
                                        "code": t.get("code"),
                                        "name": t.get("name"),
                                        "developer_name": t.get("developer_name"),
                                        "data_sample": d.get("data"),
                                    }
                                if v117172 is not None:
                                    count_117172_nonnull += 1

                        # 比較対象: どちらかに分がある選手
                        if v119 is None and v117172 is None and not present_119 and not present_117172:
                            continue

                        same = None
                        if v119 is not None and v117172 is not None:
                            compare_count += 1
                            same = abs(v119 - v117172) < 0.01
                            if same:
                                equal_count += 1

                        # 出場カテゴリの目安
                        category = "unknown"
                        m = v117172 if v117172 is not None else v119
                        if m is not None:
                            if role == "start" and m >= 90:
                                category = "フル出場寄り"
                            elif role == "start" and m < 90:
                                category = "先発・途中交代寄り"
                            elif role == "bench" and m > 0:
                                category = "途中出場"
                            elif m == 0:
                                category = "出場なし"

                        rows.append(
                            {
                                "fixture_id": fid,
                                "match": fname,
                                "date": fdate,
                                "Player": pname,
                                "player_id": pid,
                                "role": role,
                                "category": category,
                                "119_present": present_119,
                                "119_data": v119,
                                "117172_data": v117172,
                                "same": same,
                                "diff": (
                                    round(v117172 - v119, 2)
                                    if v119 is not None and v117172 is not None
                                    else None
                                ),
                            }
                        )

                st.markdown("#### type 定義（レスポンスから）")
                st.write({"119": meta_119, "117172": meta_117172})

                st.markdown("#### 件数サマリー")
                st.write(
                    {
                        "行数(分情報あり)": len(rows),
                        "119がdetailsに存在した回数": count_119_present,
                        "119のdataが数値だった回数": count_119_nonnull,
                        "117172のdataが数値だった回数": count_117172_nonnull,
                        "両方数値で比較した回数": compare_count,
                        "数値が一致した回数": equal_count,
                    }
                )

                st.markdown("#### 比較一覧（全件）")
                st.dataframe(rows, use_container_width=True, hide_index=True)

                # カテゴリ別にサンプル抽出
                st.markdown("#### カテゴリ別サンプル")
                for cat in ("フル出場寄り", "先発・途中交代寄り", "途中出場"):
                    subset = [r for r in rows if r["category"] == cat]
                    st.caption(f"{cat}: {len(subset)}件")
                    if subset:
                        st.dataframe(
                            subset[:5], use_container_width=True, hide_index=True
                        )

                # 90超の行
                over = [
                    r
                    for r in rows
                    if (r["117172_data"] or 0) > 90 or (r["119_data"] or 0) > 90
                ]
                st.markdown(f"#### 90分超の行: {len(over)}件")
                if over:
                    st.dataframe(over[:15], use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"比較エラー: {e}")
