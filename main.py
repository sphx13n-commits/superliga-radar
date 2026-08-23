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
    "token_missing": "Token not found" if is_english else "トークンが見つかりません",
    "connected": "Connected to Sportmonks" if is_english else "Sportmonksに接続できました",
    "season": "Season" if is_english else "シーズン",
    "season_select": "Select a season" if is_english else "シーズンを選択",
    "team_select": "Select a team" if is_english else "チームを選択",
    "player_select": "Select a player" if is_english else "選手を選択",
    "minute_filter": "Minutes filter" if is_english else "出場時間",
    "no_team": "No teams found" if is_english else "チームが見つかりません",
    "team_list": " squad" if is_english else "の選手一覧",
    "save_hint": "Long-press the image to save it to Photos."
    if is_english
    else "下の画像を長押しすると、写真に保存できます。",
    "download": "Download PNG" if is_english else "PNGをダウンロード",
    "no_players": "No players found" if is_english else "選手データがありません",
    "no_stats": "No stats available" if is_english else "この選手のスタッツがありません",
    "all_stats": "Season API stats (debug)" if is_english else "シーズンAPIの指標（確認用）",
    "per90_note": "Values are per 90 minutes." if is_english else "数値は90分あたり。",
    "description": "Superliga player radar" if is_english else "スーペルリーガの選手レーダー",
}

st.markdown(
    """
    <style>
      .block-container { padding-top: 0.8rem; padding-bottom: 1.2rem; }
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
    57: ("Saves", "セーブ"),
    78: ("Tackles", "タックル"),
    79: ("Assists", "アシスト"),
    80: ("Passes", "パス"),
    86: ("Shots on target", "枠内シュート"),
    100: ("Interceptions", "インターセプト"),
    101: ("Clearances", "クリア"),
    107: ("Aerials won", "空中戦勝利"),
    109: ("Successful dribbles", "ドリブル成功"),
    116: ("Accurate passes", "成功パス"),
    117: ("Key passes", "キーパス"),
    119: ("Minutes", "出場時間"),
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
    return "MID"


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
                "font": {"color": NAVY, "size": sizes[i] if i < len(sizes) else 13, "family": "Arial"},
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
    season_records = [s for s in league.get("seasons", []) if s.get("id") and s.get("name")]
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
        TEXT["season_select"], season_names, index=season_names.index(default_season_name)
    )
    season_id = season_options[selected_season_name]
    season_name = selected_season_name

    teams_res = requests.get(
        f"{base_url}/teams/seasons/{season_id}", headers=headers, params=params, timeout=30
    )
    teams_data = teams_res.json()
    if teams_res.status_code != 200:
        st.error(f"チーム取得エラー: {teams_res.status_code}")
        st.stop()

    st.success(TEXT["connected"])
    st.caption(f"{TEXT['season']}: {season_name}")

    teams = teams_data.get("data", [])
    team_options = {t.get("name", "Unknown"): t.get("id") for t in teams if t.get("id")}
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
    players = [p for p in all_players if minute_filter == 0 or get_minutes(p) >= minute_filter]
    st.subheader(f"{selected_team_name}{TEXT['team_list']}")
    st.caption(f"対象: {len(players)} / 全{len(all_players)}")

    if players:
        player_options = {p["name"]: p["id"] for p in players if p.get("id")}
        selected_player_name = st.selectbox(TEXT["player_select"], sorted(player_options))
        selected_player = next(p for p in players if p.get("id") == player_options[selected_player_name])
        details = [d for s in get_season_statistics(selected_player) for d in s.get("details", [])]
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
            st.dataframe(sorted(rows, key=lambda x: x["type_id"] or 0), use_container_width=True, hide_index=True)

        labels_en = [KNOWN_NAMES.get(i, (f"id{i}",))[0] for i in RADAR_ORDER]
        raw_values = [raw_by_id[i] if isinstance(raw_by_id.get(i), (int, float)) else 0 for i in RADAR_ORDER]
        display_values = [round(v * 90 / minutes, 2) for v in raw_values] if minutes > 0 else raw_values
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
                st.download_button(TEXT["download"], data=png, file_name=f"{selected_player_name}_radar.png", mime="image/png")
            except Exception as ie:
                st.warning(str(ie))
        else:
            st.info(TEXT["no_stats"])

except Exception as e:
    st.error(f"接続エラー: {e}")


# ============================================================
# Aggregate Prototype — value の実体を特定するデバッグ強化版
# ============================================================
st.divider()
st.subheader("Aggregate Prototype（一時）")
st.caption("detail オブジェクトの全キーを見て、数値がどこに入っているか特定します。")

_proto_token = os.getenv("SPORTMONKS_TOKEN")
if _proto_token:
    _base = "https://api.sportmonks.com/v3/football"
    _headers = {"Authorization": _proto_token}
    _params = {"api_token": _proto_token}
    _POS = {24: "GK", 25: "DEF", 26: "MID", 27: "FWD"}

    def _deep_num(obj):
        """dict/listの中から最初の数値を探す"""
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
            for k in ("total", "minutes", "minute", "value", "average", "count", "sum", "percentage"):
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
        """value / data など複数キーを試す"""
        if not isinstance(detail, dict):
            return None
        for key in ("value", "data", "values", "stat", "metrics"):
            if key in detail:
                n = _deep_num(detail[key])
                if n is not None:
                    return n
        # detail 直下に数がある場合
        return _deep_num({k: v for k, v in detail.items() if k not in ("type", "type_id", "id", "fixture_id", "player_id")})

    c1, c2, c3 = st.columns(3)
    with c1:
        start_d = st.text_input("開始日", value="2026-08-01", key="proto_start")
    with c2:
        end_d = st.text_input("終了日", value="2026-08-15", key="proto_end")
    with c3:
        max_fx = st.number_input("最大試合数", min_value=1, max_value=5, value=2, key="proto_max")

    if st.button("3〜5試合を集計する", key="proto_run"):
        try:
            between_res = requests.get(
                f"{_base}/fixtures/between/{start_d}/{end_d}",
                headers=_headers,
                params={**_params, "filters": "fixtureLeagues:271"},
                timeout=30,
            )
            between_json = between_res.json()
            if between_res.status_code != 200:
                st.error(f"between 失敗: {between_res.status_code}")
            else:
                selected = (between_json.get("data") or [])[: int(max_fx)]
                st.write(f"使用Fixture数: {len(selected)}")

                fixture_rows = []
                aggs = {}
                sample_details = []  # 生detailを数件
                nonnull_examples = []

                for fx in selected:
                    fid = fx.get("id")
                    fname = fx.get("name") or str(fid)
                    fdate = (fx.get("starting_at") or "")[:10]
                    fixture_rows.append({"fixture_id": fid, "match": fname, "date": fdate})

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
                    st.caption(f"fixture {fid}: lineups={len(lineups)} / {fname}")

                    for lu in lineups:
                        pid = lu.get("player_id")
                        if not pid:
                            continue
                        pname = (lu.get("player") or {}).get("name") or lu.get("player_name") or f"id:{pid}"
                        pos_id = lu.get("position_id") or ((lu.get("player") or {}).get("position_id"))
                        details = lu.get("details") or []

                        # lineup キー一覧（最初の1人分）
                        if len(sample_details) == 0:
                            sample_details.append(
                                {
                                    "lineup_keys": sorted(list(lu.keys())),
                                    "details_count": len(details),
                                    "first_detail_full": details[0] if details else None,
                                    "detail_119": next((d for d in details if d.get("type_id") == 119), None),
                                    "detail_80": next((d for d in details if d.get("type_id") == 80), None),
                                    "detail_52": next((d for d in details if d.get("type_id") == 52), None),
                                }
                            )

                        if pid not in aggs:
                            aggs[pid] = {
                                "player_name": pname,
                                "position_id": pos_id,
                                "minutes": 0.0,
                                "raw": {},
                                "fixture_count": 0,
                                "nonnull_stats": 0,
                            }
                        aggs[pid]["fixture_count"] += 1

                        for d in details:
                            tid = d.get("type_id")
                            parsed = _extract_stat(d)
                            if parsed is not None and len(nonnull_examples) < 15:
                                t = d.get("type") or {}
                                nonnull_examples.append(
                                    {
                                        "player": pname,
                                        "type_id": tid,
                                        "code": t.get("code"),
                                        "parsed": parsed,
                                        "keys": list(d.keys()),
                                    }
                                )
                            if tid == 119 and parsed is not None:
                                aggs[pid]["minutes"] += parsed
                            elif tid is not None and parsed is not None:
                                aggs[pid]["raw"][tid] = aggs[pid]["raw"].get(tid, 0.0) + parsed
                                aggs[pid]["nonnull_stats"] += 1

                st.markdown("#### ① Fixture一覧")
                st.dataframe(fixture_rows, use_container_width=True, hide_index=True)

                st.markdown("#### 生detail構造（最重要）")
                st.write(sample_details)

                st.markdown("#### valueがNULLでなかった例（最大15）")
                if nonnull_examples:
                    st.write(nonnull_examples)
                else:
                    st.error(
                        "数値を1件も抽出できませんでした。"
                        "lineups.details の value/data が空の可能性があります。"
                    )

                st.markdown(f"#### ② 選手数: {len(aggs)}")
                with_mins = sum(1 for a in aggs.values() if a["minutes"] > 0)
                with_stats = sum(1 for a in aggs.values() if a["nonnull_stats"] > 0)
                st.caption(f"Minutes>0: {with_mins}人 / 何らかのスタッツ>0: {with_stats}人")

                sample = []
                for a in aggs.values():
                    mins = a["minutes"]
                    raw = a["raw"]

                    def p90(tid):
                        if mins <= 0:
                            return None
                        return round(raw.get(tid, 0.0) * 90 / mins, 2)

                    passes = raw.get(80, 0.0)
                    acc = raw.get(116, 0.0)
                    sample.append(
                        {
                            "Player": a["player_name"],
                            "Pos": _POS.get(a["position_id"], a["position_id"]),
                            "Minutes": int(round(mins)),
                            "Fixtures": a["fixture_count"],
                            "Goals/90": p90(52),
                            "Shots/90": p90(42),
                            "Passes/90": p90(80),
                            "Pass Acc %": round(acc / passes * 100, 1) if passes else None,
                            "Key Passes/90": p90(117),
                            "Tackles/90": p90(78),
                            "Intercepts/90": p90(100),
                            "Clearances/90": p90(101),
                            "Aerials/90": p90(107),
                            "Succ. Dribbles/90": p90(109),
                            "Ball Recovery/90": p90(27271),
                            "raw_stat_hits": a["nonnull_stats"],
                        }
                    )
                sample.sort(key=lambda x: (x["Minutes"], x["raw_stat_hits"]), reverse=True)
                st.markdown("#### ③ Aggregate サンプル")
                st.dataframe(sample[:40], use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Prototype エラー: {e}")
