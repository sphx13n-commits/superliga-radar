import os

import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="Superliga Radar", layout="centered")

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
    "description": "Superliga teams and players"
    if is_english
    else "Superligaのチームと選手",
    "token_missing": "Token not found"
    if is_english
    else "トークンが見つかりません",
    "connected": "Connected to Sportmonks"
    if is_english
    else "Sportmonksに接続できました",
    "season": "Current season" if is_english else "現在のシーズン",
    "season_id": "Season ID" if is_english else "シーズンID",
    "season_select": "Select a season" if is_english else "シーズンを選択してください",
    "team_select": "Select a team" if is_english else "チームを選択してください",
    "player_select": "Select a player"
    if is_english
    else "選手を選択してください",
    "minute_filter": "Filter by playing time"
    if is_english
    else "出場時間で絞り込む",
    "no_team": "No teams found for this season"
    if is_english
    else "このシーズンのチームが見つかりません",
    "team_list": "Team players" if is_english else "の選手一覧",
    "target_players": "Eligible players"
    if is_english
    else "対象選手",
    "all_players": "all" if is_english else "全",
    "player_chart": "Player radar chart"
    if is_english
    else "のレーダーチャート",
    "stats": "Stats" if is_english else "指標",
    "per90_note": "Values are stats per 90 minutes."
    if is_english
    else "数値は90分あたりのスタッツです",
    "player_name": "Player" if is_english else "選手名",
    "minutes": "Playing time" if is_english else "出場時間",
    "download": "Download image" if is_english else "画像をダウンロード",
    "no_players": "No player data found"
    if is_english
    else "選手データがありません",
    "no_stats": "No stats available for this player"
    if is_english
    else "この選手のスタッツがありません",
}

st.title(TEXT["title"])
st.write(TEXT["description"])

token = os.getenv("SPORTMONKS_TOKEN")

if not token:
    st.error(TEXT["token_missing"])
    st.stop()

headers = {"Authorization": token}
params = {"api_token": token}
base_url = "https://api.sportmonks.com/v3/football"
default_season_id = 27897
season_id = default_season_id

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
STATISTIC_NAMES_EN = {
    52: "Goals",
    79: "Assists",
    194: "Shots",
    214: "Tackles",
    215: "Interceptions",
    216: "Clearances",
    321: "Aerials Won",
    322: "Successful Dribbles",
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
    # リーグID 271（Superliga）のシーズン一覧と現在シーズンを取得
    league_res = requests.get(
        f"{base_url}/leagues/271",
        headers=headers,
        params={**params, "include": "currentSeason;seasons"},
        timeout=15,
    )
    league_data = league_res.json()

    if league_res.status_code != 200:
        st.error(f"リーグ情報の取得エラー: {league_res.status_code}")
        st.write(league_data)
        st.stop()

    league = league_data.get("data", {})
    current_season = league.get("currentseason") or league.get("currentSeason") or {}
    season_records = [
        season
        for season in league.get("seasons", [])
        if season.get("id") and season.get("name")
    ]
    if not season_records and current_season.get("id"):
        season_records = [current_season]
    if not season_records:
        st.error("No seasons found" if is_english else "シーズンが見つかりません")
        st.stop()

    season_records.sort(
        key=lambda season: (
            season.get("id") == current_season.get("id"),
            season.get("starting_at", ""),
        ),
        reverse=True,
    )
    season_options = {
        season["name"]: season["id"]
        for season in season_records
    }
    season_names = list(season_options)
    default_season_name = next(
        (
            season["name"]
            for season in season_records
            if season["id"] == default_season_id
        ),
        current_season.get("name", season_names[0]),
    )
    selected_season_name = st.selectbox(
        TEXT["season_select"],
        season_names,
        index=season_names.index(default_season_name),
    )
    season_id = season_options[selected_season_name]
    season_name = selected_season_name

    # 選択したシーズンに所属するチーム一覧を取得
    teams_res = requests.get(
        f"{base_url}/teams/seasons/{season_id}",
        headers=headers,
        params=params,
        timeout=15,
    )
    teams_data = teams_res.json()

    if teams_res.status_code != 200:
        st.error(
            f"Team list error: {teams_res.status_code}"
            if is_english
            else f"チーム一覧の取得エラー: {teams_res.status_code}"
        )
        st.write(teams_data)
        st.stop()

    st.success(TEXT["connected"])
    st.subheader(f"{TEXT['season']}: {season_name}")
    st.caption(f"{TEXT['season_id']}: {season_id}")

    teams = teams_data.get("data", [])
    if not teams:
        st.info(TEXT["no_team"])
        st.stop()

    team_options = {
        team.get("name", "名前未設定"): team.get("id")
        for team in teams
        if team.get("id")
    }
    selected_team_name = st.selectbox(
        TEXT["team_select"],
        list(team_options),
    )
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
        st.error(
            f"Player list error: {squad_res.status_code}"
            if is_english
            else f"選手一覧の取得エラー: {squad_res.status_code}"
        )
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
        format_func=lambda value: (
            f"{value}+ minutes" if is_english and value
            else "Any playing time" if is_english
            else f"{value}分以上" if value
            else "指定なし"
        ),
    )
    players = [
        player
        for player in all_players
        if minute_filter == 0 or get_minutes(player) >= minute_filter
    ]

    st.subheader(f"{selected_team_name}{TEXT['team_list']}")
    if is_english:
        st.caption(
            f"{TEXT['target_players']}: {len(players)} / "
            f"{TEXT['all_players']} {len(all_players)}"
        )
    else:
        st.caption(f"対象選手: {len(players)}人 / 全{len(all_players)}人")
    if players:
        player_options = {
            player["name"]: player["id"]
            for player in players
            if player.get("id")
        }
        selected_player_name = st.selectbox(
            TEXT["player_select"],
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
        radar_names = STATISTIC_NAMES_EN if is_english else STATISTIC_NAMES
        for detail in statistic_details:
            type_id = detail.get("type_id")
            value = get_total_value(detail)
            if (
                type_id in RADAR_STATISTIC_IDS
                and isinstance(value, (int, float))
            ):
                radar_values[radar_names[type_id]] = value

        st.subheader(f"{selected_player_name}{TEXT['player_chart']}")
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
                scale_label = (
                    "Raw values (no playing time)"
                    if is_english
                    else "実数値（出場時間なし）"
                )

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
                title={
                    "text": f"{TEXT['stats']} ({scale_label})",
                    "font": {"size": 18},
                },
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
            st.caption(TEXT["per90_note"])
            try:
                png_data = figure.to_image(
                    format="png",
                    width=900,
                    height=1100,
                    scale=2,
                )
                st.download_button(
                    label=TEXT["download"],
                    data=png_data,
                    file_name=f"{selected_player_name}_radar.png",
                    mime="image/png",
                )
            except Exception as image_error:
                st.warning(
                    f"Image export error: {image_error}"
                    if is_english
                    else f"画像の生成エラー: {image_error}"
                )
            st.write(f"{TEXT['player_name']}: {selected_player_name}")
            st.write(
                f"{TEXT['minutes']}: "
                f"{minutes}{' minutes' if is_english else '分'}"
            )
        else:
            st.info(TEXT["no_stats"])
    else:
        st.info(TEXT["no_players"])

except Exception as e:
    st.error(
        f"Connection error: {e}" if is_english else f"接続エラー: {e}"
    )