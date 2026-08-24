import base64
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(
    page_title="Superliga Radar",
    page_icon="⚽",
    layout="centered",
)

NAVY = "#0B1F3A"
NAVY_SOFT = "rgba(11, 31, 58, 0.32)"
ACCENT = "#C45C26"
ACCENT_SOFT = "rgba(196, 92, 38, 0.28)"
GRID = "#B8C7D9"
AXIS = "#6B82A0"
BG = "#EEF2F7"
WHITE = "#FFFFFF"
RING_100 = "#3D5A80"
MINUTES_TYPE_ID = 119
LEAGUE_ID = 271
CACHE_ROOT = Path(__file__).with_name("cache") / "superliga"
POSITION_MAP = {24: "GK", 25: "DEF", 26: "MID", 27: "FWD"}
MAX_BETWEEN_DAYS = 90
MAX_SEASONS = 3
SMALL_SAMPLE_N = 15

BAND_ELITE = "#5C7A9A"
BAND_STRONG = "#8BB0F5"
BAND_AVG = "#C5D0DE"
BAND_BELOW = "#E4E9F0"


def percentile_band(p):
    if p is None:
        return "—", BAND_AVG
    if p >= 90:
        return "Elite", BAND_ELITE
    if p >= 70:
        return "Strong", BAND_STRONG
    if p >= 30:
        return "Average", BAND_AVG
    return "Below", BAND_BELOW


def fmt_num(x, kind="raw"):
    if x is None:
        return "—"
    if isinstance(x, str):
        return x
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if kind == "pct":
        s = f"{v:.1f}"
    elif kind == "per90":
        s = f"{v:.2f}"
    else:
        if abs(v - round(v)) < 1e-9:
            return str(int(round(v)))
        s = f"{v:.2f}"
    s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def fmt_radar_label(v, is_ratio=False):
    if v is None:
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if is_ratio:
        s = f"{x:.1f}"
    else:
        if abs(x) >= 10:
            s = f"{x:.1f}"
        else:
            s = f"{x:.2f}"
    return s.rstrip("0").rstrip(".") or "0"


POSITION_METRICS = {
    "GK": [
        {"key": "saves_p90", "label": "Saves/90", "tid": 57, "kind": "per90"},
        {"key": "saves_box_p90", "label": "Saves Box/90", "tid": 104, "kind": "per90"},
        {"key": "conceded_p90", "label": "Conc./90", "tid": 88, "kind": "lower_better_per90"},
        {"key": "pass_acc", "label": "Pass Acc %", "kind": "ratio", "num": 116, "den": 80},
        {"key": "acc_pass_p90", "label": "Acc Pass/90", "tid": 116, "kind": "per90"},
        {"key": "long_p90", "label": "Long Balls/90", "tid": 122, "kind": "per90"},
        {"key": "recovery_p90", "label": "Recovery/90", "tid": 27271, "kind": "per90"},
    ],
    "DEF": [
        {"key": "tackles_p90", "label": "Tackles/90", "tid": 78, "kind": "per90"},
        {"key": "int_p90", "label": "Intercepts/90", "tid": 100, "kind": "per90"},
        {"key": "clear_p90", "label": "Clearances/90", "tid": 101, "kind": "per90"},
        {"key": "aerial_p90", "label": "Aerials/90", "tid": 107, "kind": "per90"},
        {"key": "pass_acc", "label": "Pass Acc %", "kind": "ratio", "num": 116, "den": 80},
        {"key": "acc_pass_p90", "label": "Acc Pass/90", "tid": 116, "kind": "per90"},
        {"key": "passes_p90", "label": "Passes/90", "tid": 80, "kind": "per90"},
        {"key": "succ_drib_p90", "label": "Succ Drib/90", "tid": 109, "kind": "per90"},
        {"key": "recovery_p90", "label": "Recovery/90", "tid": 27271, "kind": "per90"},
        {"key": "fouls_p90", "label": "Fouls/90", "tid": 56, "kind": "lower_better_per90"},
    ],
    "MID": [
        {"key": "passes_p90", "label": "Passes/90", "tid": 80, "kind": "per90"},
        {"key": "pass_acc", "label": "Pass Acc %", "kind": "ratio", "num": 116, "den": 80},
        {"key": "key_p90", "label": "Key Pass/90", "tid": 117, "kind": "per90"},
        {"key": "assists_p90", "label": "Assists/90", "tid": 79, "kind": "per90"},
        {"key": "goals_p90", "label": "Goals/90", "tid": 52, "kind": "per90"},
        {"key": "shots_p90", "label": "Shots/90", "tid": 42, "kind": "per90"},
        {"key": "tackles_p90", "label": "Tackles/90", "tid": 78, "kind": "per90"},
        {"key": "int_p90", "label": "Intercepts/90", "tid": 100, "kind": "per90"},
        {"key": "succ_drib_p90", "label": "Succ Drib/90", "tid": 109, "kind": "per90"},
        {"key": "recovery_p90", "label": "Recovery/90", "tid": 27271, "kind": "per90"},
    ],
    "FWD": [
        {"key": "goals_p90", "label": "Goals/90", "tid": 52, "kind": "per90"},
        {"key": "assists_p90", "label": "Assists/90", "tid": 79, "kind": "per90"},
        {"key": "shots_p90", "label": "Shots/90", "tid": 42, "kind": "per90"},
        {"key": "sot_p90", "label": "SOT/90", "tid": 86, "kind": "per90"},
        {"key": "key_p90", "label": "Key Pass/90", "tid": 117, "kind": "per90"},
        {"key": "drib_att_p90", "label": "Drib Att/90", "tid": 108, "kind": "per90"},
        {"key": "succ_drib_p90", "label": "Succ Drib/90", "tid": 109, "kind": "per90"},
        {"key": "aerial_p90", "label": "Aerials/90", "tid": 107, "kind": "per90"},
        {"key": "pass_acc", "label": "Pass Acc %", "kind": "ratio", "num": 116, "den": 80},
        {"key": "recovery_p90", "label": "Recovery/90", "tid": 27271, "kind": "per90"},
    ],
}

_, lang_col = st.columns([4, 1])
with lang_col:
    language = st.selectbox(
        "Language", ["日本語", "English"], index=0, label_visibility="collapsed"
    )
is_en = language == "English"

T = {
    "tagline": (
        "Explore Danish Superliga players with position-specific percentile radars."
        if is_en
        else "デンマーク・スーペルリーガの選手を、ポジション別Percentileレーダーで探索。"
    ),
    "season": "Season" if is_en else "シーズン",
    "filters": "Filters" if is_en else "フィルター",
    "min_minutes": "Minimum minutes" if is_en else "最低出場時間",
    "team": "Team" if is_en else "チーム",
    "all_teams": "All teams" if is_en else "すべてのチーム",
    "player": "Player" if is_en else "選手",
    "compare": "Compare with another player (same position)"
    if is_en
    else "別の選手と比較（同ポジション）",
    "player_b": "Compare with" if is_en else "比較相手",
    "radar": "Percentile radar" if is_en else "Percentileレーダー",
    "stats": "Statistics" if is_en else "スタッツ詳細",
    "download": "Download PNG" if is_en else "PNGをダウンロード",
    "update": "Update data" if is_en else "データ更新",
    "force": "Force re-fetch all fixtures (rarely needed)"
    if is_en
    else "全Fixtureを強制再取得（通常は不要）",
    "updating": "Updating..." if is_en else "更新中...",
    "no_data": "No data yet." if is_en else "データがありません。",
    "no_fixtures": "No finished fixtures found." if is_en else "終了試合が取得できませんでした。",
    "no_players": "No players match the filters." if is_en else "条件に合う選手がいません。",
    "no_compare": "No other players in this position."
    if is_en
    else "同ポジションに比較できる選手がいません。",
    "pct_title": "What is Percentile?" if is_en else "Percentileとは？",
    "pct_body": (
        "Same-position ranking 0–100 under the minute filter.\n\n"
        "Bands: Elite 90+ · Strong 70–89 · Average 30–69 · Below <30\n\n"
        "Shape = percentile · Bold ring = 100 · Labels = Per90 (single view)."
        if is_en
        else "同ポジション・出場時間条件での順位（0–100）。\n\n"
        "帯: Elite 90+ · Strong 70–89 · Average 30–69 · Below 30未満\n\n"
        "形 = Percentile · 太い円 = 100の上限 · 数字 = Per90（単体時）。"
    ),
    "early_note": (
        "Early season: overall sample is still building — treat percentiles as indicative."
        if is_en
        else "シーズン序盤は全体の母集団がまだ小さいため、Percentileは参考値として見てください。"
    ),
    "small_sample": (
        "⚠ Small sample (n={n}) — percentile ranks can swing a lot."
        if is_en
        else "⚠ 母集団が小さいです（n={n}）。Percentileは参考値として見てください。"
    ),
    "band_legend": (
        "Elite 90+ · Strong 70–89 · Average 30–69 · Below <30"
        if is_en
        else "Elite 90+ · Strong 70–89 · Average 30–69 · Below 30未満"
    ),
    "method_title": "Data & methodology" if is_en else "データと計算方法",
    "admin_title": "Data maintenance" if is_en else "データメンテナンス",
    "last_updated": "Last updated" if is_en else "最終更新",
    "connected": "Connected" if is_en else "接続済み",
    "apps": "Apps" if is_en else "出場数",
    "season_loading": "Loading..." if is_en else "読み込み中...",
}

st.markdown(
    f"""
    <div style="background:{NAVY};padding:18px 16px 14px;border-radius:14px;margin-bottom:14px;">
      <div style="color:white;font-size:26px;font-weight:750;">Superliga Radar</div>
      <div style="color:#C9D4E3;font-size:13px;margin-top:6px;">{T["tagline"]}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

token = os.getenv("SPORTMONKS_TOKEN")
if not token:
    st.error("Token not found" if is_en else "トークンが見つかりません")
    st.stop()

headers = {"Authorization": token}
params = {"api_token": token}
base_url = "https://api.sportmonks.com/v3/football"
default_season_id = 27897


def _deep_num(obj):
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
        for k in ("total", "minutes", "value", "average", "count", "sum", "percentage"):
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
    if not isinstance(detail, dict):
        return None
    for key in ("data", "value", "values"):
        if key in detail:
            n = _deep_num(detail[key])
            if n is not None:
                return n
    return None


def _cache_dir(sid):
    d = CACHE_ROOT / f"season_{sid}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _is_finished_fixture(fx):
    state = fx.get("state") or {}
    state_id = fx.get("state_id") or state.get("id")
    name = (
        state.get("short_name")
        or state.get("name")
        or state.get("developer_name")
        or ""
    ).upper()
    if state_id in (5, 7, 8):
        return True
    if name in ("FT", "FULL TIME", "FINISHED", "AET", "FT_PEN"):
        return True
    return bool(fx.get("result_info") or fx.get("scores"))


def get_logo_data_uri():
    p = Path(__file__).with_name("logo.png")
    if not p.exists():
        return None
    return f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def format_updated_at(iso_str):
    if not iso_str:
        return "—"
    try:
        s = str(iso_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(iso_str)[:19]


def _parse_ymd(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _date_chunks(start_s, end_s, max_days=MAX_BETWEEN_DAYS):
    start = _parse_ymd(start_s)
    end = _parse_ymd(end_s)
    if end < start:
        end = start
    chunks = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days - 1), end)
        chunks.append((cur.isoformat(), chunk_end.isoformat()))
        cur = chunk_end + timedelta(days=1)
    return chunks


def build_radar_figure(
    labels,
    values_a,
    title_lines,
    footnotes,
    display_texts=None,
    values_b=None,
    name_a=None,
    name_b=None,
):
    """
    形 = Percentile 0–100
    軸 = 0–122（外側はラベル用）
    太い線 = 100 の境界（カテゴリ軸で描画）
    """
    fig = go.Figure()
    n = len(labels)
    theta = labels + [labels[0]]

    # 1) データ先（カテゴリ軸を確定）
    r_a = values_a + [values_a[0]]
    fig.add_trace(
        go.Scatterpolar(
            r=r_a,
            theta=theta,
            fill="toself",
            fillcolor=NAVY_SOFT,
            line={"color": NAVY, "width": 3.4},
            marker={"color": NAVY, "size": 11, "line": {"color": WHITE, "width": 1.2}},
            mode="lines+markers",
            name=name_a or "A",
            hovertemplate="%{theta}: %{r:.0f}<extra>" + (name_a or "A") + "</extra>",
        )
    )

    if values_b is not None:
        r_b = values_b + [values_b[0]]
        fig.add_trace(
            go.Scatterpolar(
                r=r_b,
                theta=theta,
                fill="toself",
                fillcolor=ACCENT_SOFT,
                line={"color": ACCENT, "width": 3.4},
                marker={
                    "color": ACCENT,
                    "size": 11,
                    "line": {"color": WHITE, "width": 1.2},
                },
                mode="lines+markers",
                name=name_b or "B",
                hovertemplate="%{theta}: %{r:.0f}<extra>" + (name_b or "B") + "</extra>",
            )
        )

    # 2) Percentile 100 境界（同じ labels＝カテゴリ。数値の度は使わない）
    fig.add_trace(
        go.Scatterpolar(
            r=[100.0] * (n + 1),
            theta=theta,
            mode="lines",
            line={"color": RING_100, "width": 2.6},
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # 3) 単体時のみ Per90
    if values_b is None and display_texts is not None:
        OUTER_R = 108
        fig.add_trace(
            go.Scatterpolar(
                r=[OUTER_R] * (n + 1),
                theta=theta,
                mode="text",
                text=list(display_texts) + [display_texts[0]],
                textfont={
                    "size": 18,
                    "color": NAVY,
                    "family": "Arial Black, Arial, sans-serif",
                },
                hoverinfo="skip",
                showlegend=False,
            )
        )

    annotations = []
    title_sizes = [44, 20, 16]
    title_ys = [0.985, 0.938, 0.905]
    for i, line in enumerate(title_lines):
        annotations.append(
            {
                "text": f"<b>{line}</b>" if i == 0 else line,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": title_ys[i] if i < len(title_ys) else 0.88,
                "xanchor": "center",
                "yanchor": "top",
                "showarrow": False,
                "font": {
                    "color": NAVY,
                    "size": title_sizes[i] if i < len(title_sizes) else 15,
                    "family": "Arial",
                },
            }
        )

    if values_b is not None:
        annotations.append(
            {
                "text": (
                    f"<span style='color:{NAVY}'><b>■ {name_a}</b></span>"
                    f"　　<span style='color:{ACCENT}'><b>■ {name_b}</b></span>"
                ),
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.148,
                "xanchor": "center",
                "yanchor": "top",
                "showarrow": False,
                "font": {"size": 15, "family": "Arial"},
            }
        )

    base_y = 0.110 if values_b is None else 0.100
    for i, line in enumerate(footnotes or []):
        annotations.append(
            {
                "text": line,
                "xref": "paper",
                "yref": "paper",
                "x": 0.03,
                "y": base_y - i * 0.024,
                "xanchor": "left",
                "yanchor": "top",
                "showarrow": False,
                "font": {"color": "#374151", "size": 14, "family": "Arial"},
            }
        )

    annotations.append(
        {
            "text": "<b>@Dalaprospect</b>",
            "xref": "paper",
            "yref": "paper",
            "x": 0.97,
            "y": 0.018,
            "xanchor": "right",
            "yanchor": "bottom",
            "showarrow": False,
            "font": {"color": NAVY, "size": 15, "family": "Arial"},
        }
    )

    images = []
    logo = get_logo_data_uri()
    if logo:
        images.append(
            {
                "source": logo,
                "xref": "paper",
                "yref": "paper",
                "x": 0.97,
                "y": 0.048,
                "sizex": 0.085,
                "sizey": 0.085,
                "xanchor": "right",
                "yanchor": "bottom",
                "sizing": "contain",
                "layer": "above",
            }
        )

    fig.update_layout(
        height=1500,
        width=1200,
        margin={"l": 120, "r": 120, "t": 155, "b": 170},
        paper_bgcolor=WHITE,
        plot_bgcolor=WHITE,
        showlegend=False,
        images=images,
        annotations=annotations,
        polar={
            "domain": {"x": [0.15, 0.85], "y": [0.19, 0.80]},
            "bgcolor": BG,
            "radialaxis": {
                "visible": True,
                "range": [0, 122],
                "tickvals": [0, 20, 40, 60, 80, 100],
                "gridcolor": GRID,
                "linecolor": AXIS,
                "tickfont": {"color": AXIS, "size": 13},
            },
            "angularaxis": {
                "gridcolor": GRID,
                "linecolor": AXIS,
                "tickfont": {"color": NAVY, "size": 13, "family": "Arial"},
                "rotation": 90,
                "direction": "clockwise",
            },
        },
    )
    return fig


def percentile_rank(values, target, higher_is_better=True):
    n = len(values)
    if n <= 1:
        return 50.0
    if higher_is_better:
        below = sum(1 for v in values if v < target)
        equal = sum(1 for v in values if v == target)
    else:
        below = sum(1 for v in values if v > target)
        equal = sum(1 for v in values if v == target)
    return round(100.0 * (below + (equal - 1) / 2.0) / (n - 1), 1)


def compute_metrics(raw, minutes, metric_defs):
    out = {}
    for m in metric_defs:
        if m["kind"] in ("per90", "lower_better_per90"):
            out[m["key"]] = (
                round(raw.get(m["tid"], 0.0) * 90.0 / minutes, 3)
                if minutes > 0
                else None
            )
        elif m["kind"] == "ratio":
            den = raw.get(m["den"], 0.0)
            num = raw.get(m["num"], 0.0)
            out[m["key"]] = round(num / den * 100.0, 2) if den > 0 else None
    return out


def style_percentile_col(val):
    try:
        p = float(val)
    except (TypeError, ValueError):
        return ""
    if p >= 90:
        color, text = "#0B1F3A", "#FFFFFF"
    elif p >= 70:
        color, text = "#2F6FED", "#FFFFFF"
    elif p >= 30:
        color, text = "#B7C4D6", NAVY
    else:
        color, text = "#E6EBF2", NAVY
    return f"background-color: {color}; color: {text}; font-weight: 700;"


def player_key(g):
    return f"{g.get('Player')}|{g.get('Team')}|{g.get('Pos')}|{g.get('Minutes')}"


league_res = requests.get(
    f"{base_url}/leagues/{LEAGUE_ID}",
    headers=headers,
    params={**params, "include": "currentSeason;seasons"},
    timeout=30,
)
if league_res.status_code != 200:
    st.error(f"League error: {league_res.status_code}")
    st.stop()

league = league_res.json().get("data", {})
current_season = league.get("currentseason") or league.get("currentSeason") or {}
season_records = [
    s for s in league.get("seasons", []) if s.get("id") and s.get("name")
]
if not season_records and current_season.get("id"):
    season_records = [current_season]

season_records.sort(
    key=lambda s: (
        s.get("id") == current_season.get("id"),
        s.get("starting_at") or "",
    ),
    reverse=True,
)
season_records = season_records[:MAX_SEASONS]

season_options = {s["name"]: s["id"] for s in season_records}
season_meta = {s["id"]: s for s in season_records}
season_names = list(season_options)

default_name = next(
    (s["name"] for s in season_records if s["id"] == default_season_id),
    None,
)
if default_name is None:
    default_name = next(
        (s["name"] for s in season_records if s["id"] == current_season.get("id")),
        season_names[0] if season_names else "",
    )

st.markdown(f"##### {T['season']}")
selected_season_name = st.selectbox(
    T["season"],
    season_names,
    index=season_names.index(default_name) if default_name in season_names else 0,
    label_visibility="collapsed",
)
season_id = season_options[selected_season_name]
season_name = selected_season_name
season_info = season_meta.get(season_id, {})

if st.session_state.get("loaded_season_id") != season_id:
    st.session_state.fx_aggs = None
    st.session_state.fx_status = None
    st.session_state.fx_errors = []
    st.session_state.loaded_season_id = season_id

teams_res = requests.get(
    f"{base_url}/teams/seasons/{season_id}",
    headers=headers,
    params=params,
    timeout=30,
)
teams = teams_res.json().get("data", []) if teams_res.status_code == 200 else []
team_id_to_name = {
    t.get("id"): (t.get("name") or str(t.get("id")))
    for t in teams
    if t.get("id") is not None
}


def _paginate_fixtures_window(start, end, filter_str=None):
    all_fx, page, errors = [], 1, 0
    last_status = None
    while True:
        req_params = {
            **params,
            "include": "state;participants;scores",
            "page": page,
        }
        if filter_str:
            req_params["filters"] = filter_str
        res = requests.get(
            f"{base_url}/fixtures/between/{start}/{end}",
            headers=headers,
            params=req_params,
            timeout=40,
        )
        last_status = res.status_code
        if res.status_code != 200:
            errors = 1
            break
        body = res.json() or {}
        all_fx.extend(body.get("data") or [])
        if not (body.get("pagination") or {}).get("has_more"):
            break
        page += 1
        if page > 30:
            break
        time.sleep(0.05)
    return all_fx, (0 if last_status == 200 else 1), last_status, None


def _fetch_between_chunked(start_s, end_s, filter_str=None):
    chunks = _date_chunks(start_s, end_s, MAX_BETWEEN_DAYS)
    all_fx, seen_ids = [], set()
    total_errors = 0
    last_status = None
    for w_start, w_end in chunks:
        fx, err, status, _ = _paginate_fixtures_window(w_start, w_end, filter_str)
        last_status = status
        total_errors += err
        for item in fx:
            fid = item.get("id")
            if fid is None or fid in seen_ids:
                continue
            seen_ids.add(fid)
            all_fx.append(item)
        time.sleep(0.05)
    return all_fx, total_errors, last_status, None, []


def fetch_season_fixtures_list(sid, season_meta_row):
    start = (season_meta_row.get("starting_at") or "")[:10] or "2024-07-01"
    end = (season_meta_row.get("ending_at") or "")[:10] or "2027-06-30"
    today = date.today().isoformat()
    wide_start = start
    wide_end = min(end, today) if end else today
    if wide_end < wide_start:
        wide_end = wide_start

    fx_a, err_a, st_a, _, _ = _fetch_between_chunked(
        wide_start, wide_end, f"fixtureSeasons:{sid}"
    )
    all_fx, errors = fx_a, err_a

    if len(all_fx) == 0:
        fx_b, err_b, st_b, _, _ = _fetch_between_chunked(
            wide_start, wide_end, f"fixtureLeagues:{LEAGUE_ID}"
        )
        filtered = []
        for fx in fx_b:
            fx_sid = fx.get("season_id") or (fx.get("season") or {}).get("id")
            if fx_sid is None or int(fx_sid) == int(sid):
                filtered.append(fx)
        all_fx = filtered if filtered else fx_b
        errors += err_b

    finished = [fx for fx in all_fx if _is_finished_fixture(fx)]
    if len(finished) == 0 and len(all_fx) > 0:
        finished = [
            fx
            for fx in all_fx
            if fx.get("scores")
            or fx.get("result_info")
            or fx.get("state_id") in (5, 7, 8)
        ]

    payload = {
        "season_id": sid,
        "total_fetched": len(all_fx),
        "finished_count": len(finished),
        "list_errors": errors,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "fixtures": [
            {
                "id": fx.get("id"),
                "name": fx.get("name"),
                "starting_at": fx.get("starting_at"),
            }
            for fx in finished
            if fx.get("id")
        ],
    }
    _save_json(_cache_dir(sid) / "fixtures_list.json", payload)
    return payload


def load_fixture_detail(sid, fixture_id, force_refresh=False):
    path = _cache_dir(sid) / f"fixture_{fixture_id}.json"
    if not force_refresh and path.exists():
        cached = _load_json(path)
        if cached is not None:
            return cached, "cache", None
    res = requests.get(
        f"{base_url}/fixtures/{fixture_id}",
        headers=headers,
        params={**params, "include": "lineups.details.type;participants"},
        timeout=45,
    )
    if res.status_code != 200:
        return None, "error", f"HTTP {res.status_code}"
    data = (res.json() or {}).get("data")
    _save_json(path, data)
    time.sleep(0.05)
    return data, "api", None


def aggregate_player_team(fixture_payloads, sid):
    aggs = {}
    for fdata in fixture_payloads:
        if not fdata:
            continue
        for lu in fdata.get("lineups") or []:
            pid, tid = lu.get("player_id"), lu.get("team_id")
            if not pid or not tid:
                continue
            key = f"{sid}_{pid}_{tid}"
            pname = (
                (lu.get("player") or {}).get("name")
                or lu.get("player_name")
                or f"id:{pid}"
            )
            pos_id = lu.get("position_id") or (
                (lu.get("player") or {}).get("position_id")
            )
            if key not in aggs:
                aggs[key] = {
                    "season_id": sid,
                    "player_id": pid,
                    "team_id": tid,
                    "player_name": pname,
                    "position_id": pos_id,
                    "minutes": 0.0,
                    "raw": {},
                    "apps": 0,
                }
            else:
                if pname and str(aggs[key]["player_name"]).startswith("id:"):
                    aggs[key]["player_name"] = pname
                if pos_id and not aggs[key]["position_id"]:
                    aggs[key]["position_id"] = pos_id
            played = False
            for d in lu.get("details") or []:
                type_id = d.get("type_id")
                if type_id is None:
                    continue
                parsed = _extract_stat(d)
                if parsed is None:
                    continue
                if type_id == MINUTES_TYPE_ID:
                    aggs[key]["minutes"] += parsed
                    if parsed > 0:
                        played = True
                else:
                    aggs[key]["raw"][type_id] = (
                        aggs[key]["raw"].get(type_id, 0.0) + parsed
                    )
            if played:
                aggs[key]["apps"] += 1
    return aggs


def restore_aggs_from_file(sid):
    cached = _load_json(_cache_dir(sid) / "player_team_aggregate.json")
    if not cached:
        return None, None
    if cached.get("season_id") not in (None, sid):
        try:
            if int(cached.get("season_id")) != int(sid):
                return None, None
        except (TypeError, ValueError):
            pass
    players = cached.get("players")
    if not isinstance(players, list) or not players:
        return None, None
    restored = {}
    for p in players:
        if not isinstance(p, dict):
            continue
        pid, tid = p.get("player_id"), p.get("team_id")
        if not pid or not tid:
            continue
        key = f"{sid}_{pid}_{tid}"
        raw_in = p.get("raw") or {}
        raw_out = {}
        if isinstance(raw_in, dict):
            for k, v in raw_in.items():
                try:
                    raw_out[int(k)] = float(v) if v is not None else 0.0
                except (TypeError, ValueError):
                    continue
        restored[key] = {
            "season_id": sid,
            "player_id": pid,
            "team_id": tid,
            "player_name": p.get("player_name") or f"id:{pid}",
            "position_id": p.get("position_id"),
            "minutes": float(p.get("minutes") or 0),
            "apps": p.get("apps") or 0,
            "raw": raw_out,
        }
    if not restored:
        return None, None
    meta = {
        "players": len(restored),
        "updated_at": cached.get("updated_at"),
        "finished_fixtures": cached.get("finished_fixtures"),
        "mode": "cache_file",
        "season_id": sid,
    }
    return restored, meta


def save_aggs(sid, aggs, status):
    rows_out = [
        {
            "player_id": a["player_id"],
            "team_id": a["team_id"],
            "player_name": a["player_name"],
            "position_id": a["position_id"],
            "minutes": a["minutes"],
            "apps": a["apps"],
            "raw": {str(k): v for k, v in a["raw"].items()},
        }
        for a in aggs.values()
    ]
    safe_status = {k: v for k, v in (status or {}).items() if k != "players"}
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "season_id": sid,
        "updated_at": now,
        "player_count": len(aggs),
        "players": rows_out,
        **safe_status,
    }
    _save_json(_cache_dir(sid) / "player_team_aggregate.json", payload)
    return payload


def incremental_update(sid, season_meta_row, force_all=False):
    cdir = _cache_dir(sid)
    flist = fetch_season_fixtures_list(sid, season_meta_row)
    finished_ids = [f["id"] for f in flist.get("fixtures", [])]
    finished_count = len(finished_ids)

    cached_ids, missing_ids = [], []
    for fid in finished_ids:
        path = cdir / f"fixture_{fid}.json"
        if path.exists() and not force_all:
            cached_ids.append(fid)
        else:
            missing_ids.append(fid)

    loaded, new_fetched, errors = [], 0, []
    for fid in cached_ids:
        data = _load_json(cdir / f"fixture_{fid}.json")
        if data is not None:
            loaded.append(data)

    prog = st.progress(0.0) if missing_ids else None
    for i, fid in enumerate(missing_ids):
        data, source, err = load_fixture_detail(sid, fid, force_refresh=force_all)
        if err:
            errors.append({"fixture_id": fid, "error": err})
        elif data is not None:
            loaded.append(data)
            if source == "api":
                new_fetched += 1
        if prog:
            prog.progress((i + 1) / max(len(missing_ids), 1))

    agg_path = cdir / "player_team_aggregate.json"
    need_rebuild = (
        force_all
        or new_fetched > 0
        or (not agg_path.exists())
        or restore_aggs_from_file(sid)[0] is None
        or finished_count == 0
    )
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if not need_rebuild and agg_path.exists():
        aggs, meta = restore_aggs_from_file(sid)
        if aggs is not None:
            return (
                aggs,
                {
                    "finished_fixtures": finished_count,
                    "new_fetched": 0,
                    "players": len(aggs),
                    "updated_at": (meta or {}).get("updated_at") or now,
                    "mode": "incremental_skip_rebuild",
                    "season_id": sid,
                },
                errors,
            )

    aggs = aggregate_player_team(loaded, sid)
    status = {
        "finished_fixtures": finished_count,
        "new_fetched": new_fetched,
        "players": len(aggs),
        "mode": "rebuild",
        "season_id": sid,
        "updated_at": now,
    }
    save_aggs(sid, aggs, status)
    return aggs, status, errors


if st.session_state.get("fx_aggs") is None:
    with st.spinner(T["season_loading"]):
        aggs, meta = restore_aggs_from_file(season_id)
        if aggs is not None:
            st.session_state.fx_aggs = aggs
            st.session_state.fx_status = meta or {
                "players": len(aggs),
                "mode": "cache_file",
                "season_id": season_id,
            }
            st.session_state.fx_errors = []
        else:
            aggs, status, errors = incremental_update(
                season_id, season_info, force_all=False
            )
            st.session_state.fx_aggs = aggs
            st.session_state.fx_status = status
            st.session_state.fx_errors = errors

aggs = st.session_state.get("fx_aggs")
status = st.session_state.get("fx_status") or {}

st.caption(
    f"{T['connected']} · {T['last_updated']}: **{format_updated_at(status.get('updated_at'))}** · "
    f"Players: {status.get('players') or (len(aggs) if aggs else 0)} · Season ID: {season_id}"
)

if not aggs:
    st.warning(T["no_fixtures"] if status.get("finished_fixtures") == 0 else T["no_data"])
else:
    st.markdown(f"##### {T['filters']}")
    f1, f2 = st.columns(2)
    with f1:
        min_min = st.selectbox(T["min_minutes"], [0, 300, 600, 900], index=1)

    by_pos = {p: [] for p in ("GK", "DEF", "MID", "FWD")}
    for a in aggs.values():
        mins = a["minutes"]
        if mins < float(min_min) or mins <= 0:
            continue
        pos = POSITION_MAP.get(a["position_id"])
        if pos not in by_pos:
            continue
        metrics = compute_metrics(a["raw"], mins, POSITION_METRICS[pos])
        team_name = team_id_to_name.get(a["team_id"]) or (
            str(a["team_id"]) if a["team_id"] is not None else "Unknown"
        )
        by_pos[pos].append(
            {
                "Player": a["player_name"] or f"id:{a['player_id']}",
                "Team": team_name,
                "Pos": pos,
                "Minutes": int(round(mins)),
                "Apps": a["apps"],
                "metrics": metrics,
                "raw": a["raw"],
            }
        )

    for pos, group in by_pos.items():
        for m in POSITION_METRICS[pos]:
            vals = [
                g["metrics"][m["key"]]
                for g in group
                if g["metrics"].get(m["key"]) is not None
            ]
            higher = m["kind"] != "lower_better_per90"
            for g in group:
                v = g["metrics"].get(m["key"])
                g.setdefault("pct", {})[m["key"]] = (
                    None if v is None else percentile_rank(vals, v, higher)
                )

    all_players = [g for pos in by_pos.values() for g in pos]
    teams_in = sorted(
        {str(g["Team"]) for g in all_players if g.get("Team") not in (None, "")}
    )
    with f2:
        team_filter = st.selectbox(T["team"], [T["all_teams"]] + teams_in)
    if team_filter != T["all_teams"]:
        all_players = [g for g in all_players if g["Team"] == team_filter]

    n_total = sum(len(v) for v in by_pos.values())
    n_by_pos = {p: len(by_pos[p]) for p in ("GK", "DEF", "MID", "FWD")}
    st.caption(
        f"n={n_total} · GK{n_by_pos['GK']} / DEF{n_by_pos['DEF']} / "
        f"MID{n_by_pos['MID']} / FWD{n_by_pos['FWD']}"
    )
    if 0 < n_total < 40:
        st.info(T["early_note"])
    tiny_pos = [p for p, n in n_by_pos.items() if 0 < n < SMALL_SAMPLE_N]
    if tiny_pos:
        st.caption(
            ("Small position samples: " if is_en else "母集団が小さいポジション: ")
            + ", ".join(f"{p} n={n_by_pos[p]}" for p in tiny_pos)
        )

    if not all_players:
        st.warning(T["no_players"])
    else:
        all_players.sort(key=lambda g: (g["Player"] or "").lower())
        labels_a = [
            f"{g['Player']} · {g['Team']} · {g['Pos']} · {g['Minutes']}′"
            for g in all_players
        ]
        st.markdown(f"##### {T['player']}")
        choice_a = st.selectbox(
            T["player"], labels_a, key="player_a", label_visibility="collapsed"
        )
        selected_a = all_players[labels_a.index(choice_a)]
        pos = selected_a["Pos"]
        mdefs = POSITION_METRICS[pos]
        n_pos = len(by_pos[pos])
        is_small = n_pos < SMALL_SAMPLE_N

        do_compare = st.checkbox(T["compare"], value=False)
        selected_b = None
        if do_compare:
            peers = [
                g for g in by_pos[pos] if player_key(g) != player_key(selected_a)
            ]
            peers.sort(key=lambda g: (g["Player"] or "").lower())
            if not peers:
                st.warning(T["no_compare"])
            else:
                labels_b = [
                    f"{g['Player']} · {g['Team']} · {g['Minutes']}′" for g in peers
                ]
                choice_b = st.selectbox(T["player_b"], labels_b, key="player_b")
                selected_b = peers[labels_b.index(choice_b)]

        if selected_b is None:
            st.markdown(
                f"""
                <div style="border:1px solid #D7E0EC;border-radius:12px;padding:14px 16px;margin:8px 0 14px;background:#F8FAFC;">
                  <div style="font-size:22px;font-weight:750;color:{NAVY};">{selected_a['Player']}</div>
                  <div style="margin-top:6px;color:#334155;font-size:14px;">
                    {selected_a['Team']} · <b>{pos}</b> · {selected_a['Minutes']} min · {T['apps']} {selected_a['Apps']}
                  </div>
                  <div style="margin-top:4px;color:#64748B;font-size:12px;">Superliga {season_name}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(
                    f"""
                    <div style="border:2px solid {NAVY};border-radius:12px;padding:12px;background:#F8FAFC;">
                      <div style="font-size:11px;color:{NAVY};font-weight:700;">A</div>
                      <div style="font-size:18px;font-weight:750;color:{NAVY};">{selected_a['Player']}</div>
                      <div style="font-size:13px;color:#334155;">{selected_a['Team']} · {selected_a['Minutes']}′</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    f"""
                    <div style="border:2px solid {ACCENT};border-radius:12px;padding:12px;background:#FFF8F5;">
                      <div style="font-size:11px;color:{ACCENT};font-weight:700;">B</div>
                      <div style="font-size:18px;font-weight:750;color:{ACCENT};">{selected_b['Player']}</div>
                      <div style="font-size:13px;color:#334155;">{selected_b['Team']} · {selected_b['Minutes']}′</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if is_small:
            st.warning(T["small_sample"].format(n=n_pos))

        with st.expander(T["pct_title"], expanded=False):
            st.markdown(T["pct_body"])
            st.caption(T["band_legend"])

        st.markdown(f"##### {T['radar']}")

        radar_labels = [m["label"] for m in mdefs]
        values_a = [selected_a.get("pct", {}).get(m["key"]) or 0 for m in mdefs]
        display_a = [
            fmt_radar_label(
                selected_a["metrics"].get(m["key"]),
                is_ratio=(m["kind"] == "ratio"),
            )
            for m in mdefs
        ]
        values_b = None
        if selected_b is not None:
            values_b = [selected_b.get("pct", {}).get(m["key"]) or 0 for m in mdefs]

        sample_line = f"Sample: {pos}, ≥{int(min_min)} min (n={n_pos})"
        if is_small:
            sample_line += " · ⚠ Small sample" if is_en else " · ⚠ 母集団小・参考値"

        if selected_b is None:
            footnotes = [
                f"Shape = percentile (0–100) · Bold ring = 100 · Labels = Per90/% · {sample_line}",
                "Bands: Elite 90+ · Strong 70–89 · Average 30–69 · Below <30",
                "Per90 uses Minutes Played · Fixture aggregate",
                f"Superliga {season_name} · Superliga Radar · Data: Sportmonks API",
            ]
            title_lines = [
                selected_a["Player"],
                f"{selected_a['Team']} | {pos} | {selected_a['Minutes']} min",
                f"Superliga {season_name} · Percentile radar",
            ]
            fig = build_radar_figure(
                radar_labels,
                values_a,
                title_lines,
                footnotes,
                display_texts=display_a,
                name_a=selected_a["Player"],
            )
        else:
            footnotes = [
                f"Overlay = percentile (0–100) · Bold ring = 100 · {sample_line}",
                f"Navy = {selected_a['Player']} · Orange = {selected_b['Player']}",
                "Same position only · Numbers in table below",
                f"Superliga {season_name} · Superliga Radar · Data: Sportmonks API",
            ]
            title_lines = [
                f"{selected_a['Player']}  vs  {selected_b['Player']}",
                f"{pos} · Superliga {season_name}",
                "Percentile comparison",
            ]
            fig = build_radar_figure(
                radar_labels,
                values_a,
                title_lines,
                footnotes,
                display_texts=None,
                values_b=values_b,
                name_a=selected_a["Player"],
                name_b=selected_b["Player"],
            )

        try:
            png = fig.to_image(format="png", width=1200, height=1500, scale=2)
            st.image(png, use_container_width=True)
            st.caption(T["band_legend"])
            fname = selected_a["Player"].replace(" ", "_")
            if selected_b is not None:
                fname += "_vs_" + selected_b["Player"].replace(" ", "_")
            st.download_button(
                T["download"],
                data=png,
                file_name=f"{fname}_superliga_radar.png",
                mime="image/png",
            )
        except Exception as e:
            st.warning(str(e))

        st.markdown(f"##### {T['stats']}")
        rows = []
        for m in mdefs:
            row = {"Metric": m["label"]}
            row["A Per90/%"] = fmt_num(selected_a["metrics"].get(m["key"]), "per90")
            row["A %ile"] = fmt_num(selected_a.get("pct", {}).get(m["key"]), "pct")
            if selected_b is not None:
                row["B Per90/%"] = fmt_num(
                    selected_b["metrics"].get(m["key"]), "per90"
                )
                row["B %ile"] = fmt_num(
                    selected_b.get("pct", {}).get(m["key"]), "pct"
                )
            else:
                raw_v = (
                    selected_a["raw"].get(m["tid"], 0)
                    if m["kind"] in ("per90", "lower_better_per90")
                    else (
                        f"{fmt_num(selected_a['raw'].get(m['num'], 0))} / "
                        f"{fmt_num(selected_a['raw'].get(m['den'], 0))}"
                    )
                )
                row["Raw"] = (
                    raw_v if isinstance(raw_v, str) else fmt_num(raw_v, "raw")
                )
                band_name, _ = percentile_band(
                    selected_a.get("pct", {}).get(m["key"])
                )
                row["Band"] = band_name
            rows.append(row)

        df = pd.DataFrame(rows)
        pct_cols = [c for c in df.columns if "%ile" in c]
        if pct_cols:
            st.dataframe(
                df.style.map(style_percentile_col, subset=pct_cols),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

with st.expander(T["method_title"], expanded=False):
    st.markdown(
        "形=Percentile(0–100) · 太い円=100の上限 · 外側はPer90用余白"
        if not is_en
        else "Shape=percentile 0–100 · Bold ring=100 · Outer margin for Per90 labels"
    )

with st.expander(T["admin_title"], expanded=False):
    force_all = st.checkbox(T["force"], value=False)
    if st.button(T["update"], type="primary"):
        with st.spinner(T["updating"]):
            aggs2, status2, errors2 = incremental_update(
                season_id, season_info, force_all=force_all
            )
            st.session_state.fx_aggs = aggs2
            st.session_state.fx_status = status2
            st.session_state.fx_errors = errors2
            st.session_state.loaded_season_id = season_id
            st.rerun()
    st.write(
        {
            "season_id": season_id,
            "players": status.get("players") or (len(aggs) if aggs else 0),
            "updated_at": status.get("updated_at"),
            "mode": status.get("mode"),
        }
    )
