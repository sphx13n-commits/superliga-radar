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

    # 選択したチームのシーズン別選手一覧を取得
    squad_res = requests.get(
        f"{base_url}/squads/seasons/{season_id}/teams/{selected_team_id}",
        headers=headers,
        params={**params, "include": "player"},
        timeout=15,
    )
    squad_data = squad_res.json()

    if squad_res.status_code != 200:
        st.error(f"選手一覧の取得エラー: {squad_res.status_code}")
        st.write(squad_data)
        st.stop()

    players = [
        squad.get("player", {})
        for squad in squad_data.get("data", [])
        if squad.get("player", {}).get("name")
    ]

    st.subheader(f"{selected_team_name}の選手一覧")
    if players:
        for player in players:
            st.write(f"- {player['name']}")
    else:
        st.info("選手データがありません")

except Exception as e:
    st.error(f"接続エラー: {e}")