import os

import requests
import streamlit as st

st.set_page_config(page_title="Superliga Radar", layout="centered")
st.title("Superliga Radar")
st.write("Superligaの現在シーズンと所属チーム")

token = os.getenv("SPORTMONKS_TOKEN")

if not token:
    st.error("トークンが見つかりません")
    st.stop()

headers = {"Authorization": token}
params = {"api_token": token}
base_url = "https://api.sportmonks.com/v3/football"

try:
    # リーグID 271（Superliga）の現在シーズンを取得
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
    # Sportmonksのレスポンスでは currentseason が小文字で返る場合がある
    season = league.get("currentseason") or league.get("currentSeason")

    if not season or not season.get("id"):
        st.error("現在のシーズン情報が見つかりません")
        st.write(league_data)
        st.stop()

    season_id = season["id"]
    season_name = season.get("name") or f"シーズンID: {season_id}"

    # 現在シーズンに所属するチーム一覧を取得
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
    st.write(f"チーム数: {len(teams)}")

    if teams:
        for team in teams:
            st.write(f"- {team.get('name', '名前未設定')}")
    else:
        st.info("このシーズンのチームが見つかりません")

except Exception as e:
    st.error(f"接続エラー: {e}")