import os

import requests
import streamlit as st

st.set_page_config(page_title="Superliga Radar", layout="centered")
st.title("Superliga Radar")
st.write("Sportmonks接続テスト")

token = os.getenv("SPORTMONKS_TOKEN")

if not token:
    st.error("トークンが見つかりません")
    st.stop()

# リーグ一覧を取得して確認
url = "https://api.sportmonks.com/v3/football/leagues"
headers = {"Authorization": token}  # または api_token パラメータでも可
params = {"api_token": token}

try:
    res = requests.get(url, headers=headers, params=params, timeout=15)
    data = res.json()

    if res.status_code == 200:
        st.success("Sportmonksに接続できました")
        leagues = data.get("data", [])
        st.write(f"取得できたリーグ数: {len(leagues)}")

        # 名前に Superliga や Denmark が含まれるものを表示
        for league in leagues[:20]:
            name = league.get("name", "")
            st.write(f"- {name} (ID: {league.get('id')})")
    else:
        st.error(f"エラー: {res.status_code}")
        st.write(data)

except Exception as e:
    st.error(f"接続エラー: {e}")