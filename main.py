import os

import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="Superliga Radar", layout="centered")
st.title("Superliga Radar")
st.write("Superligaのチームと選手")

token = os.getenv("SPORTMONKS_TOKEN")

if not token:
    st.error("トークンが見つかりません")
    st.stop()

headers = {"Authorization": token}
params = {"api_token": token}
base_url = "https://api.sportmonks.com/v3/football"
season_id = 27897

# Sportmonksの統計項目ID。APIから項目名が返らないため、対応できるものだけ日本語化する。
STATISTIC_NAMES = {
    52: "ゴール",
    79: "アシスト",
    88: "出場数",
    119: "出場時間（分）",
    194: "シュート",
    214: "タックル",
    215: "インターセプト",
    216: "クリア",
    321: "空中戦勝利",
    322: "ドリブル成功",
}
RADAR_STATISTIC_IDS = {
    52,
    79,
    194,
    214,
    215,
    216,
    321,
    322,
}


def get_total_value(detail):
    value = detail.get("value")
    if isinstance(value, dict):
        return value.get("total")
    return value


def get_season_statistics(player):
    return [
        statistic
        for statistic in player.get("statistics", [])
        if statistic.get("season_id") == season_id
    ]


def get_minutes(player):
    for statistic in get_season_statistics(player):
        for detail in statistic.get("details", []):
            if detail.get("type_id") == 119:
                value = get_total_value(detail)
                return value if isinstance(value, (int, float)) else 0
    return 0


try:
    # リーグID 271（Superliga）のシーズン名を取得
    league_res = requests.get(
        f"{base_url}/leagues/271",
        headers=headers,
        params={**params, "include": "currentSeason"},
        timeout=15,
    )
    league_data = league_res.json()

    if league_res.status_code != 200:
        st.error(f"リーグ情報の取得エラー: {league_res.status_code}")
        st.write(league_data)
        st.stop()

    league = league_data.get("data", {})
    current_season = league.get("currentseason") or league.get("currentSeason") or {}
    season_name = current_season.get("name") or f"シーズンID: {season_id}"

    # シーズン27897に所属するチーム一覧を取得
    teams_res = requests.get(
        f"{base_url}/teams/seasons/{season_id}",
        headers=headers,
        params=params,
        timeout=15,
    )
    teams_data = teams_res.json()

    if teams_res.status_code != 200:
        st.error(f"チーム一覧の取得エラー: {teams_res.status_code}")
        st.write(teams_data)
        st.stop()

    st.success("Sportmonksに接続できました")
    st.subheader(f"現在のシーズン: {season_name}")
    st.caption(f"シーズンID: {season_id}")

    teams = teams_data.get("data", [])
    if not teams:
        st.info("このシーズンのチームが見つかりません")
        st.stop()

    team_options = {
        team.get("name", "名前未設定"): team.get("id")
        for team in teams
        if team.get("id")
    }
    selected_team_name = st.selectbox("チームを選択してください", list(team_options))
    selected_team_id = team_options[selected_team_name]

    # 選択したチームのシーズン別選手一覧とスタッツを取得
    squad_res = requests.get(
        f"{base_url}/squads/seasons/{season_id}/teams/{selected_team_id}",
        headers=headers,
        params={**params, "include": "player.statistics.details"},
        timeout=15,
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
        "出場時間で絞り込む",
        options=[900, 600, 300, 0],
        format_func=lambda value: (
            f"{value}分以上" if value else "指定なし"
        ),
    )
    players = [
        player
        for player in all_players
        if minute_filter == 0 or get_minutes(player) >= minute_filter
    ]

    st.subheader(f"{selected_team_name}の選手一覧")
    st.caption(f"対象選手: {len(players)}人 / 全{len(all_players)}人")
    if players:
        player_options = {
            player["name"]: player["id"]
            for player in players
            if player.get("id")
        }
        selected_player_name = st.selectbox(
            "選手を選択してください",
            list(player_options),
        )
        selected_player = next(
            player
            for player in players
            if player.get("id") == player_options[selected_player_name]
        )
        season_statistics = [
            statistic
            for statistic in get_season_statistics(selected_player)
        ]
        statistic_details = [
            detail
            for statistic in season_statistics
            for detail in statistic.get("details", [])
            if detail.get("value") is not None
        ]

        radar_values = {}
        for detail in statistic_details:
            type_id = detail.get("type_id")
            value = get_total_value(detail)
            if (
                type_id in RADAR_STATISTIC_IDS
                and isinstance(value, (int, float))
            ):
                radar_values[STATISTIC_NAMES[type_id]] = value

        st.subheader(f"{selected_player_name}のレーダーチャート")
        if radar_values:
            minutes = get_minutes(selected_player)
            display_values = list(radar_values.values())
            if minutes > 0:
                display_values = [
                    round(value * 90 / minutes, 2)
                    for value in display_values
                ]
                scale_label = "per90"
            else:
                scale_label = "実数値（出場時間なし）"

            labels = list(radar_values)
            chart_labels = labels + [labels[0]]
            chart_values = display_values + [display_values[0]]
            figure = go.Figure(
                go.Scatterpolar(
                    r=chart_values,
                    theta=chart_labels,
                    fill="toself",
                    fillcolor="rgba(15, 45, 85, 0.22)",
                    line={"color": "#0f2d55", "width": 3},
                    marker={"color": "#0f2d55", "size": 7},
                )
            )
            figure.update_layout(
                height=680,
                margin={"l": 40, "r": 40, "t": 45, "b": 45},
                paper_bgcolor="white",
                plot_bgcolor="white",
                font={"color": "#0f2d55", "size": 14},
                showlegend=False,
                title={"text": f"指標（{scale_label}）", "font": {"size": 18}},
                polar={
                    "bgcolor": "white",
                    "radialaxis": {
                        "visible": True,
                        "gridcolor": "#d9e2ef",
                        "linecolor": "#9fb2ca",
                        "tickfont": {"color": "#48617e"},
                    },
                    "angularaxis": {
                        "gridcolor": "#d9e2ef",
                        "linecolor": "#9fb2ca",
                        "tickfont": {"color": "#0f2d55", "size": 14},
                    },
                },
            )
            st.plotly_chart(
                figure,
                use_container_width=True,
                config={"displayModeBar": False},
            )
            st.write(f"選手名: {selected_player_name}")
            st.write(f"出場時間: {minutes}分")
        else:
            st.info("この選手のスタッツがありません")
    else:
        st.info("選手データがありません")

except Exception as e:
    st.error(f"接続エラー: {e}")