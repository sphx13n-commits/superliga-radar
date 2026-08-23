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
    "title": "Superliga Radar",
    "description": "Superliga player radar charts"
    if is_english
    else "スーペルリーガの選手レーダー",
    "token_missing": "Token not found" if is_english else "トークンが見つかりません",
    "connected": "Connected to Sportmonks" if is_english else "Sportmonksに接続できました",
    "season": "Season" if is_english else "シーズン",
    "season_select": "Select a season" if is_english else "シーズンを選択",
    "team_select": "Select a team" if is_english else "チームを選択",
    "player_select": "Select a player" if is_english else "選手を選択",
    "minute_filter": "Minutes filter" if is_english else "出場時間",
    "no_team": "No teams found" if is_english else "チームが見つかりません",
    "team_list": " squad" if is_english else "の選手一覧",
    "target_players": "Shown" if is_english else "対象選手",
    "all_players": "total" if is_english else "全",
    "per90_note": "Values are per 90 minutes (not percentiles)."
    if is_english
    else "数値は90分あたり（パーセンタイルではありません）。",
    "save_hint": "Long-press the image to save it to Photos."
    if is_english
    else "下の画像を長押しすると、写真に保存できます。",
    "download": "Download PNG" if is_english else "PNGをダウンロード",
    "no_players": "No players found" if is_english else "選手データがありません",
    "no_stats": "No stats available" if is_english else "この選手のスタッツがありません",
    "all_stats": "Season API stats (debug)"
    if is_english
    else "シーズンAPIの指標（確認用）",
}

st.markdown(
    """
    <style>
      .block-container { padding-top: 0.8rem; padding-bottom: 1.2rem; }
      div[data-testid="stVerticalBlock"] > div { gap: 0.25rem !important; }
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
    56: ("Fouls", "ファウル"),
    57: ("Saves", "セーブ"),
    78: ("Tackles", "タックル"),
    79: ("Assists", "アシスト"),
    80: ("Passes", "パス"),
    84: ("Yellow cards", "警告"),
    86: ("Shots on target", "枠内シュート"),
    88: ("Goals conceded", "失点"),
    100: ("Interceptions", "インターセプト"),
    101: ("Clearances", "クリア"),
    104: ("Saves inside box", "PA内セーブ"),
    107: ("Aerials won", "空中戦勝利"),
    108: ("Dribble attempts", "ドリブル試行"),
    109: ("Successful dribbles", "ドリブル成功"),
    116: ("Accurate passes", "成功パス"),
    117: ("Key passes", "キーパス"),
    118: ("Rating", "レーティング"),
    119: ("Minutes", "出場時間"),
    122: ("Long balls", "ロングボール"),
    1584: ("Pass accuracy %", "パス成功率"),
    194: ("Clean sheets", "無失点"),
    214: ("Team wins", "勝利"),
    215: ("Team draws", "引き分け"),
    216: ("Team losses", "敗戦"),
    321: ("Appearances", "出場数"),
    322: ("Lineups", "先発数"),
    27271: ("Ball recovery", "ボール回収"),
}

RADAR_ORDER = [52, 79, 42, 78, 100, 101, 107, 109]
POSITION_MAP = {24: "GK", 25: "DEF", 26: "MID", 27: "FWD"}


def get_total_value(detail):
    value = detail.get("value")
    if isinstance(value, dict):
        for k in ("total", "minutes", "average", "percentage", "value", "count"):
            if k in value and isinstance(value[k], (int, float)):
                return value[k]
        for v in value.values():
            if isinstance(v, (int, float)):
                return v
        return None
    return value


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
    if pid in POSITION_MAP:
        return POSITION_MAP[pid]
    pos = player.get("position") or player.get("detailed_position") or {}
    if isinstance(pos, dict):
        if pos.get("id") in POSITION_MAP:
            return POSITION_MAP[pos.get("id")]
        name = str(pos.get("name") or pos.get("developer_name") or "").upper()
        if "GOAL" in name or name == "GK":
            return "GK"
        if "DEF" in name or "BACK" in name:
            return "DEF"
        if "MID" in name:
            return "MID"
        if "ATT" in name or "FWD" in name or "FORW" in name or "WING" in name:
            return "FWD"
    return "MID"


def known_name(type_id):
    if type_id in KNOWN_NAMES:
        en, ja = KNOWN_NAMES[type_id]
        return en if is_english else ja
    return f"type_id {type_id}"


def get_logo_data_uri():
    logo_path = Path(__file__).with_name("logo.png")
    logo_bytes = logo_path.read_bytes()
    return f"data:image/png;base64,{base64.b64encode(logo_bytes).decode('ascii')}"


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
            marker={
                "color": WHITE,
                "size": 10,
                "line": {"color": NAVY, "width": 2.5},
            },
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
        font={"color": NAVY, "size": 14, "family": "Arial"},
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
                "tickfont": {"color": AXIS, "size": 12, "family": "Arial"},
                "showline": True,
            },
            "angularaxis": {
                "gridcolor": GRID,
                "linecolor": AXIS,
                "tickfont": {"color": NAVY, "size": 16, "family": "Arial"},
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
        st.error(f"リーグ情報の取得エラー: {league_res.status_code}")
        st.stop()

    league = league_data.get("data", {})
    current_season = league.get("currentseason") or league.get("currentSeason") or {}
    season_records = [
        s for s in league.get("seasons", []) if s.get("id") and s.get("name")
    ]
    if not season_records and current_season.get("id"):
        season_records = [current_season]
    if not season_records:
        st.error("シーズンが見つかりません")
        st.stop()

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
        st.error(f"チーム一覧の取得エラー: {teams_res.status_code}")
        st.stop()

    st.success(TEXT["connected"])
    st.caption(f"{TEXT['season']}: {season_name}")

    teams = teams_data.get("data", [])
    if not teams:
        st.info(TEXT["no_team"])
        st.stop()

    team_options = {
        team.get("name", "Unknown"): team.get("id") for team in teams if team.get("id")
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
        st.error(f"選手一覧の取得エラー: {squad_res.status_code}")
        st.stop()

    all_players = [
        squad.get("player", {})
        for squad in squad_data.get("data", [])
        if squad.get("player", {}).get("name")
    ]

    minute_filter = st.selectbox(
        TEXT["minute_filter"],
        options=[900, 600, 300, 0],
        format_func=lambda v: (
            f"{v}+ min"
            if is_english and v
            else "Any"
            if is_english
            else f"{v}分以上"
            if v
            else "指定なし"
        ),
    )
    players = [
        p for p in all_players if minute_filter == 0 or get_minutes(p) >= minute_filter
    ]

    st.subheader(f"{selected_team_name}{TEXT['team_list']}")
    st.caption(
        f"対象選手: {len(players)}人 / 全{len(all_players)}人"
        if not is_english
        else f"Shown: {len(players)} / total {len(all_players)}"
    )

    if players:
        player_options = {p["name"]: p["id"] for p in players if p.get("id")}
        selected_player_name = st.selectbox(TEXT["player_select"], sorted(player_options))
        selected_player = next(
            p for p in players if p.get("id") == player_options[selected_player_name]
        )

        details = [
            d
            for s in get_season_statistics(selected_player)
            for d in s.get("details", [])
        ]
        raw_by_id = {}
        all_stats_rows = []
        for d in details:
            tid = d.get("type_id")
            val = get_total_value(d)
            if tid is None:
                continue
            raw_by_id[tid] = val
            all_stats_rows.append(
                {"type_id": tid, "name": known_name(tid), "value": val}
            )
        all_stats_rows = sorted(all_stats_rows, key=lambda x: x["type_id"] or 0)

        minutes = get_minutes(selected_player)
        age = calc_age(
            selected_player.get("date_of_birth")
            or selected_player.get("dateOfBirth")
            or selected_player.get("birthday")
        )
        position = get_position_label(selected_player)
        age_text = f"{age}" if age is not None else "-"

        st.markdown(
            f"""
            <div style="background:{WHITE};border:1px solid {CARD_BORDER};
            border-left:5px solid {NAVY};border-radius:10px;padding:10px 12px 8px;margin:2px 0 8px;">
              <div style="font-size:22px;font-weight:800;color:{NAVY};">{selected_player_name}</div>
              <div style="margin-top:4px;font-size:13px;color:{AXIS};font-weight:600;">
                {selected_team_name} | {position} | {age_text}{" yrs" if is_english else "歳"} | {minutes}{" min" if is_english else "分"}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander(TEXT["all_stats"]):
            if all_stats_rows:
                st.dataframe(all_stats_rows, use_container_width=True, hide_index=True)
            else:
                st.warning("statistics.details が空です")

        labels_en = [KNOWN_NAMES.get(i, (f"id{i}",))[0] for i in RADAR_ORDER]
        raw_values = [
            raw_by_id[i] if isinstance(raw_by_id.get(i), (int, float)) else 0
            for i in RADAR_ORDER
        ]
        if minutes > 0:
            display_values = [round(v * 90 / minutes, 2) for v in raw_values]
            scale_label = "per90"
        else:
            display_values = list(raw_values)
            scale_label = "raw"

        if sum(display_values) != 0:
            radial_max = max(max(display_values) * 1.15, 1.0)
            title_lines = [
                selected_player_name,
                f"{selected_team_name} | {position} | {age_text} yrs | {minutes} min",
                f"Superliga {season_name} · {scale_label} (season API)",
            ]
            fig_export = build_radar_figure(
                labels_en, display_values, title_lines, radial_max
            )
            try:
                png_data = fig_export.to_image(
                    format="png", width=900, height=1180, scale=2
                )
                st.markdown(f"**{TEXT['save_hint']}**")
                st.image(png_data, use_container_width=True)
                st.caption(TEXT["per90_note"] + " ※暫定: シーズンAPI")
                st.download_button(
                    TEXT["download"],
                    data=png_data,
                    file_name=f"{selected_player_name}_radar.png",
                    mime="image/png",
                )
            except Exception as image_error:
                st.warning(f"画像エラー: {image_error}")
        else:
            st.info(TEXT["no_stats"])

except Exception as e:
    st.error(f"接続エラー: {e}")


# ============================================================
# Aggregate Prototype（Minutes取得を強化）
# ============================================================
st.divider()
st.subheader("Aggregate Prototype（一時）")
st.caption("最大5試合の lineups.details を合算。Minutes=0 問題の切り分け付き。")

_proto_token = os.getenv("SPORTMONKS_TOKEN")
if _proto_token:
    _base = "https://api.sportmonks.com/v3/football"
    _headers = {"Authorization": _proto_token}
    _params = {"api_token": _proto_token}
    _POS = {24: "GK", 25: "DEF", 26: "MID", 27: "FWD"}

    def _num(v):
        """value の様々な形から数値を取り出す"""
        if v is None:
            return None
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return None
        if isinstance(v, dict):
            for k in (
                "total",
                "minutes",
                "minute",
                "average",
                "percentage",
                "value",
                "count",
                "sum",
            ):
                if k in v and isinstance(v[k], (int, float)):
                    return float(v[k])
            nums = [float(x) for x in v.values() if isinstance(x, (int, float))]
            if nums:
                return float(nums[0])
        return None

    def _extract_minutes(lu, details):
        """lineup本体 → details(119) の順で出場分を探す"""
        for key in ("minutes", "minutes_played", "minute"):
            if key in lu and isinstance(lu[key], (int, float)) and lu[key] > 0:
                return float(lu[key])
        for d in details:
            if d.get("type_id") == 119:
                n = _num(d.get("value"))
                if n is not None:
                    return float(n)
        return 0.0

    c1, c2, c3 = st.columns(3)
    with c1:
        start_d = st.text_input("開始日", value="2026-08-01", key="proto_start")
    with c2:
        end_d = st.text_input("終了日", value="2026-08-15", key="proto_end")
    with c3:
        max_fx = st.number_input("最大試合数", min_value=1, max_value=5, value=4, key="proto_max")

    if st.button("3〜5試合を集計する", key="proto_run"):
        try:
            between_res = requests.get(
                f"{_base}/fixtures/between/{start_d}/{end_d}",
                headers=_headers,
                params={
                    **_params,
                    "filters": "fixtureLeagues:271",
                    "include": "participants",
                },
                timeout=30,
            )
            between_json = between_res.json()
            if between_res.status_code != 200:
                st.error(f"fixtures/between 失敗: {between_res.status_code}")
            else:
                all_fx = between_json.get("data") or []
                selected = all_fx[: int(max_fx)]
                st.write(f"使用Fixture数: {len(selected)} / 期間内ヒット: {len(all_fx)}")

                if not selected:
                    st.warning("試合がありません。")
                else:
                    fixture_rows = []
                    aggs = {}
                    debug_119_samples = []
                    debug_detail_keys = []

                    for fx in selected:
                        fid = fx.get("id")
                        fname = fx.get("name") or f"fixture {fid}"
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
                            st.warning(f"fixture {fid} 失敗: {fr.status_code}")
                            continue

                        fdata = (fr.json() or {}).get("data") or {}
                        lineups = fdata.get("lineups") or []
                        st.caption(f"fixture {fid}: lineups={len(lineups)} / {fname}")

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

                            # デバッグ: 119 の生 value を数件だけ保存
                            if len(debug_119_samples) < 5:
                                for d in details:
                                    if d.get("type_id") == 119:
                                        debug_119_samples.append(
                                            {
                                                "player": pname,
                                                "raw_value": d.get("value"),
                                                "parsed": _num(d.get("value")),
                                            }
                                        )
                                        break
                            if len(debug_detail_keys) < 3 and details:
                                d0 = details[0]
                                debug_detail_keys.append(
                                    {
                                        "type_id": d0.get("type_id"),
                                        "value_type": type(d0.get("value")).__name__,
                                        "value_sample": d0.get("value"),
                                    }
                                )

                            mins_this = _extract_minutes(lu, details)

                            if pid not in aggs:
                                aggs[pid] = {
                                    "player_id": pid,
                                    "player_name": pname,
                                    "team_id": team_id,
                                    "position_id": pos_id,
                                    "minutes": 0.0,
                                    "raw": {},
                                    "fixture_count": 0,
                                }
                            else:
                                if pname and str(aggs[pid]["player_name"]).startswith("id:"):
                                    aggs[pid]["player_name"] = pname
                                if pos_id and not aggs[pid]["position_id"]:
                                    aggs[pid]["position_id"] = pos_id

                            aggs[pid]["fixture_count"] += 1
                            aggs[pid]["minutes"] += mins_this

                            for d in details:
                                tid = d.get("type_id")
                                if tid is None or tid == 119:
                                    continue
                                val = _num(d.get("value"))
                                if val is None:
                                    continue
                                aggs[pid]["raw"][tid] = (
                                    aggs[pid]["raw"].get(tid, 0.0) + val
                                )

                    st.markdown("#### ① 使用したFixture一覧")
                    st.dataframe(fixture_rows, use_container_width=True, hide_index=True)

                    st.markdown("#### Minutes デバッグ")
                    st.caption("type_id 119 の raw value サンプル（最大5件）")
                    if debug_119_samples:
                        st.write(debug_119_samples)
                    else:
                        st.warning(
                            "type_id 119 が details に1件も見つかりませんでした。"
                            "出場時間の持ち方が異なる可能性があります。"
                        )
                    if debug_detail_keys:
                        st.caption("details[0] の value の形（参考）")
                        st.write(debug_detail_keys)

                    st.markdown(f"#### ② 集計した選手数: **{len(aggs)}**")
                    with_mins = sum(1 for a in aggs.values() if a["minutes"] > 0)
                    st.caption(f"Minutes > 0 の選手: {with_mins} 人")

                    sample = []
                    for a in aggs.values():
                        mins = a["minutes"]
                        raw = a["raw"]
                        pos = _POS.get(a["position_id"], a["position_id"])

                        def per90(tid):
                            if mins <= 0:
                                return None
                            return round(raw.get(tid, 0.0) * 90.0 / mins, 2)

                        passes = raw.get(80, 0.0)
                        acc = raw.get(116, 0.0)
                        pass_pct = (
                            round(acc / passes * 100.0, 1) if passes > 0 else None
                        )

                        sample.append(
                            {
                                "Player": a["player_name"],
                                "Pos": pos,
                                "position_id": a["position_id"],
                                "Minutes": int(round(mins)),
                                "Fixtures": a["fixture_count"],
                                "Goals/90": per90(52),
                                "Shots/90": per90(42),
                                "Passes/90": per90(80),
                                "Pass Acc %": pass_pct,
                                "Key Passes/90": per90(117),
                                "Tackles/90": per90(78),
                                "Intercepts/90": per90(100),
                                "Clearances/90": per90(101),
                                "Aerials/90": per90(107),
                                "Succ. Dribbles/90": per90(109),
                                "Ball Recovery/90": per90(27271),
                                "raw_passes": int(passes) if passes else 0,
                                "raw_acc_passes": int(acc) if acc else 0,
                            }
                        )

                    sample.sort(key=lambda x: x["Minutes"], reverse=True)

                    st.markdown("#### ③ Player Season Aggregate サンプル")
                    st.caption(
                        "Pass Acc % = Σ Accurate Passes(116) ÷ Σ Passes(80) × 100"
                    )
                    st.dataframe(sample[:40], use_container_width=True, hide_index=True)

                    multi = [s for s in sample if s["Fixtures"] >= 2]
                    st.markdown(f"複数試合の選手: **{len(multi)}** 人")
                    played = [s for s in sample if s["Minutes"] > 0]
                    st.markdown(f"Minutes>0 の上位:")
                    st.dataframe(played[:15], use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Prototype エラー: {e}")
