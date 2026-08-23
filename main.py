import base64
import os
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
    "per90_note": "Numbers on the chart are per 90 minutes (not percentiles)."
    if is_english
    else "チャート上の数字は「90分あたりの回数」です（パーセンタイルではありません）。",
    "download": "Download PNG" if is_english else "画像をダウンロード",
    "no_players": "No players found" if is_english else "選手データがありません",
    "no_stats": "No stats available" if is_english else "この選手のスタッツがありません",
    "scale_explain": "Scale: actions per 90 minutes"
    if is_english
    else "スケール：90分あたりの動作回数",
}

st.markdown(
    """
    <style>
      .block-container { padding-top: 0.8rem; padding-bottom: 1.2rem; }
      div[data-testid="stVerticalBlock"] > div { gap: 0.25rem !important; }
      .stPlotlyChart { margin-top: -1.1rem !important; margin-bottom: -0.4rem !important; }
      [data-testid="stCaption"] { margin-top: 0.2rem !important; }
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

STATISTIC_NAMES = {
    52: "ゴール",
    79: "アシスト",
    194: "シュート",
    214: "タックル",
    215: "インターセプト",
    216: "クリア",
    321: "空中戦",
    322: "ドリブル",
}
STATISTIC_NAMES_EN = {
    52: "Goals",
    79: "Assists",
    194: "Shots",
    214: "Tackles",
    215: "Intercepts",
    216: "Clearances",
    321: "Aerials",
    322: "Dribbles",
}
RADAR_ORDER = [52, 79, 194, 214, 215, 216, 321, 322]


def get_total_value(detail):
    value = detail.get("value")
    if isinstance(value, dict):
        return value.get("total")
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


def get_logo_data_uri():
    logo_path = Path(__file__).with_name("logo.png")
    logo_bytes = logo_path.read_bytes()
    encoded_logo = base64.b64encode(logo_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded_logo}"


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
        st.write(league_data)
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
        st.write(teams_data)
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
        params={**params, "include": "player.statistics.details"},
        timeout=30,
    )
    squad_data = squad_res.json()
    if squad_res.status_code != 200:
        st.error(f"選手一覧の取得エラー: {squad_res.status_code}")
        st.write(squad_data)
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
        f"{TEXT['target_players']}: {len(players)} / {TEXT['all_players']} {len(all_players)}"
        if is_english
        else f"対象選手: {len(players)}人 / 全{len(all_players)}人"
    )

    if not players:
        st.info(TEXT["no_players"])
        st.stop()

    player_options = {p["name"]: p["id"] for p in players if p.get("id")}
    selected_player_name = st.selectbox(TEXT["player_select"], sorted(player_options))
    selected_player = next(
        p for p in players if p.get("id") == player_options[selected_player_name]
    )

    details = [
        d
        for s in get_season_statistics(selected_player)
        for d in s.get("details", [])
        if d.get("value") is not None
    ]
    raw_by_id = {}
    for d in details:
        tid = d.get("type_id")
        val = get_total_value(d)
        if tid in RADAR_ORDER and isinstance(val, (int, float)):
            raw_by_id[tid] = val

    names = STATISTIC_NAMES_EN if is_english else STATISTIC_NAMES
    labels = [names[i] for i in RADAR_ORDER]
    raw_values = [raw_by_id.get(i, 0) for i in RADAR_ORDER]

    minutes = get_minutes(selected_player)
    if minutes > 0:
        display_values = [round(v * 90 / minutes, 2) for v in raw_values]
        scale_label = "per90"
    else:
        display_values = list(raw_values)
        scale_label = "raw"

    # 選手カード
    st.markdown(
        f"""
        <div style="
            background:{WHITE};
            border:1px solid {CARD_BORDER};
            border-left:5px solid {NAVY};
            border-radius:10px;
            padding:10px 12px 8px;
            margin:2px 0 0;
        ">
          <div style="font-size:22px;font-weight:800;color:{NAVY};line-height:1.2;">
            {selected_player_name}
          </div>
          <div style="margin-top:4px;font-size:13px;color:{AXIS};font-weight:600;">
            {selected_team_name}
            <span style="margin:0 6px;color:#B0BEC8;">|</span>
            {minutes}{" min" if is_english else "分"}
            <span style="margin:0 6px;color:#B0BEC8;">|</span>
            {scale_label}
          </div>
          <div style="margin-top:3px;font-size:11px;color:#8A9BB0;">
            {TEXT["scale_explain"]}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if sum(display_values) == 0:
        st.info(TEXT["no_stats"])
    else:
        chart_labels = labels + [labels[0]]
        chart_values = display_values + [display_values[0]]
        radial_max = max(max(display_values) * 1.15, 1.0)

        fig = go.Figure(
            go.Scatterpolar(
                r=chart_values,
                theta=chart_labels,
                fill="toself",
                fillcolor=NAVY_SOFT,
                line={"color": NAVY, "width": 3.5},
                marker={
                    "color": WHITE,
                    "size": 9,
                    "line": {"color": NAVY, "width": 2.5},
                },
                mode="lines+markers",
                hovertemplate="%{theta}: %{r} /90min<extra></extra>",
            )
        )

        fig.update_layout(
            height=560,
            margin={"l": 40, "r": 40, "t": 4, "b": 58},
            paper_bgcolor=WHITE,
            plot_bgcolor=WHITE,
            font={"color": NAVY, "size": 12, "family": "Arial, sans-serif"},
            showlegend=False,
            images=[
                {
                    "source": get_logo_data_uri(),
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.99,
                    "y": 0.0,
                    "sizex": 0.09,
                    "sizey": 0.09,
                    "xanchor": "right",
                    "yanchor": "bottom",
                    "sizing": "contain",
                    "layer": "above",
                }
            ],
            annotations=[
                {
                    "text": "@Dalaprospect",
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.87,
                    "y": 0.03,
                    "xanchor": "right",
                    "yanchor": "middle",
                    "showarrow": False,
                    "font": {"color": NAVY, "size": 13},
                }
            ],
            polar={
                "bgcolor": BG,
                "radialaxis": {
                    "visible": True,
                    "range": [0, radial_max],
                    "gridcolor": GRID,
                    "linecolor": AXIS,
                    "tickfont": {"color": AXIS, "size": 10},
                    "showline": True,
                },
                "angularaxis": {
                    "gridcolor": GRID,
                    "linecolor": AXIS,
                    "tickfont": {"color": NAVY, "size": 12},
                    "rotation": 90,
                    "direction": "clockwise",
                },
            },
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False},
        )
        st.caption(TEXT["per90_note"])

        # 数値一覧（意味が分かる表）
        cols = st.columns(4)
        for i, (lab, val) in enumerate(zip(labels, display_values)):
            with cols[i % 4]:
                st.metric(lab, val)

        try:
            png_data = fig.to_image(format="png", width=900, height=1000, scale=2)
            st.download_button(
                label=TEXT["download"],
                data=png_data,
                file_name=f"{selected_player_name}_radar.png",
                mime="image/png",
            )
        except Exception as image_error:
            st.warning(
                f"画像の生成エラー: {image_error}"
                if not is_english
                else f"Image export error: {image_error}"
            )

except Exception as e:
    st.error(f"接続エラー: {e}" if not is_english else f"Connection error: {e}")
