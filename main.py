import os

import streamlit as st

st.set_page_config(page_title="Superliga Radar", layout="centered")
st.title("Superliga Radar")
st.write("動作確認用の最小アプリです。")

token = os.getenv("SPORTMONKS_TOKEN")
if token:
    st.success("Sportmonksトークンを読み込めました")
else:
    st.error("トークンが見つかりません。Secretsを確認してください")