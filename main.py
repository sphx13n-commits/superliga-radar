import os

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

        st.subheader(f"{selected_player_name}のスタッツ")
        if statistic_details:
            for detail in statistic_details:
                type_id = detail.get("type_id")
                if type_id in STATISTIC_NAMES:
                    st.write(
                        f"- {STATISTIC_NAMES[type_id]}: "
                        f"{get_total_value(detail)}"
                    )
        else:
            st.info("この選手のスタッツがありません")
    else:
        st.info("選手データがありません")

except Exception as e:
    st.error(f"接続エラー: {e}")