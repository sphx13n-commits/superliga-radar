import base64
import json
import os
import time
from datetime import date, datetime, timezone
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
NAVY_SOFT = "rgba(11, 31, 58, 0.36)"
GRID = "#B8C7D9"
AXIS = "#6B82A0"
BG = "#EEF2F7"
WHITE = "#FFFFFF"
MINUTES_TYPE_ID = 119
LEAGUE_ID = 271
CACHE_ROOT = Path(__file__).with_name("cache") / "superliga"
POSITION_MAP = {24: "GK", 25: "DEF", 26: "MID", 27: "FWD"}

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
    "radar": "Percentile radar" if is_en else "Percentileレーダー",
    "stats": "Statistics" if is_en else "スタッツ詳細",
    "download": "Download PNG" if is_en else "PNGをダウンロード",
    "update": "Update data" if is_en else "データ更新",
    "force": "Force re-fetch all fixtures (rarely needed)"
    if is_en
    else "全Fixtureを強制再取得（通常は不要）",
    "updating": "Updating..." if is_en else "更新中...",
    "no_data": "No data yet. Open Data maintenance below and run Update."
    if is_en
    else "データがありません。下の「データメンテナンス」から取得してください。",
    "no_fixtures": (
        "No finished fixtures found for this season. Check methods_tried / error_body in status."
        if is_en
        else "このシーズンの終了試合が取得できませんでした。ステータスの methods_tried / error_body を確認してください。"
    ),
    "no_players": "No players match the filters. Try lowering minimum minutes."
    if is_en
    else "条件に合う選手がいません。最低出場時間を下げてください。",
    "pct_title": "What is Percentile?" if is_en else "Percentileとは？",
    "pct_body": (
        "Shows how the player ranks against others in the **same position** "
        "who meet the selected minimum-minute threshold (0–100).\n\n"
        "**Bands:** Elite 90–100 · Strong 70–89 · Average 30–69 · Below 0–29\n\n"
        "Higher is better, except **Goals Conceded/90** and **Fouls/90** "
        "(lower raw → higher percentile).\n\n"
        "Radar **shape** = percentile · vertex **labels** = Per90 (or %)."
        if is_en
        else "選択した最低出場時間を満たす**同ポジション**の選手を母集団として、"
        "位置を 0–100 で示します。\n\n"
        "**帯:** Elite 90–100 · Strong 70–89 · Average 30–69 · Below 0–29\n\n"
        "基本は高いほど良いですが、**失点/90・ファウル/90**は少ないほど高Percentileです。\n\n"
        "レーダーの**形** = Percentile · 頂点の**数字** = Per90（または%）。"
    ),
    "early_note": (
        "Early season: small samples make percentiles more volatile."
        if is_en
        else "シーズン序盤は母集団が小さいため、Percentileは参考値として見てください。"
    ),
    "band_legend": (
        "Elite 90+ · Strong 70–89 · Average 30–69 · Below <30"
        if is_en
        else "Elite 90+ · Strong 70–89 · Average 30–69 · Below 30未満"
    ),
    "method_title": "Data & methodology" if is_en else "データと計算方法",
    "status_title": "Data update status" if is_en else "データ更新ステータス",
    "admin_title": "Data maintenance" if is_en else "データメンテナンス",
    "last_updated": "Last updated" if is_en else "最終更新",
    "connected": "Connected" if is_en else "接続済み",
    "apps": "Apps" if is_en else "出場数",
    "rebuild_ok": "Aggregate rebuilt" if is_en else "Aggregate再構築",
    "skip_ok": "No new fixtures · using existing aggregate"
    if is_en
    else "新規なし · 既存Aggregateを使用",
    "season_loading": "Loading season data..." if is_en else "シーズンデータを読み込み中...",
}

st.markdown(
    f"""
    <div style="background:{NAVY};padding:18px 16px 14px;border-radius:14px;margin-bottom:14px;">
      <div style="color:white;font-size:26px;font-weight:750;letter-spacing:-0.02em;">Superliga Radar</div>
      <div style="color:#C9D4E3;font-size:13px;margin-top:6px;line-height:1.45;">{T["tagline"]}</div>
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


def build_radar_figure(labels, values, title_lines, marker_colors, footnotes, display_texts):
    r_poly = values + [values[0]]
    theta = labels + [labels[0]]
    colors_closed = marker_colors + [marker_colors[0]]

    OUTER_R = 108
    r_text = [OUTER_R] * len(values)
    r_text_closed = r_text + [r_text[0]]
    text_closed = list(display_texts) + [display_texts[0]]

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=r_poly,
            theta=theta,
            fill="toself",
            fillcolor=NAVY_SOFT,
            line={"color": NAVY, "width": 3.8},
            marker={
                "color": colors_closed,
                "size": 18,
                "line": {"color": NAVY, "width": 1.6},
            },
            mode="lines+markers",
            hovertemplate="%{theta}: %{r:.0f} pctile<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=r_text_closed,
            theta=theta,
            mode="text",
            text=text_closed,
            textfont={
                "size": 20,
                "color": NAVY,
                "family": "Arial Black, Arial, sans-serif",
            },
            hoverinfo="skip",
        )
    )

    annotations = []
    title_sizes = [48, 22, 17]
    title_ys = [0.985, 0.935, 0.900]
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
                    "size": title_sizes[i] if i < len(title_sizes) else 16,
                    "family": "Arial",
                },
            }
        )

    base_y = 0.108
    for i, line in enumerate(footnotes or []):
        annotations.append(
            {
                "text": line,
                "xref": "paper",
                "yref": "paper",
                "x": 0.03,
                "y": base_y - i * 0.026,
                "xanchor": "left",
                "yanchor": "top",
                "showarrow": False,
                "font": {"color": "#374151", "size": 15, "family": "Arial"},
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
        margin={"l": 120, "r": 120, "t": 160, "b": 170},
        paper_bgcolor=WHITE,
        plot_bgcolor=WHITE,
        showlegend=False,
        images=images,
        annotations=annotations,
        polar={
            "domain": {"x": [0.15, 0.85], "y": [0.18, 0.80]},
            "bgcolor": BG,
            "radialaxis": {
                "visible": True,
                "range": [0, 122],
                "tickvals": [0, 20, 40, 60, 80, 100],
                "gridcolor": GRID,
                "linecolor": AXIS,
                "tickfont": {"color": AXIS, "size": 14},
            },
            "angularaxis": {
                "gridcolor": GRID,
                "linecolor": AXIS,
                "tickfont": {
                    "color": NAVY,
                    "size": 14,
                    "family": "Arial",
                },
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


# ----- season list -----
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
    key=lambda s: (s.get("id") == current_season.get("id"), s.get("starting_at", "")),
    reverse=True,
)
season_options = {s["name"]: s["id"] for s in season_records}
season_meta = {s["id"]: s for s in season_records}
season_names = list(season_options)
default_name = next(
    (s["name"] for s in season_records if s["id"] == default_season_id),
    current_season.get("name", season_names[0]),
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


def _paginate_fixtures(start, end, filter_str=None):
    """fixtures/between をページング取得。エラー時は本文も返す。"""
    all_fx, page, errors = [], 1, 0
    last_status = None
    error_body = None
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
            errors += 1
            try:
                error_body = res.json()
            except Exception:
                error_body = {"raw": (res.text or "")[:800]}
            break
        body = res.json() or {}
        chunk = body.get("data") or []
        all_fx.extend(chunk)
        if not (body.get("pagination") or {}).get("has_more"):
            break
        page += 1
        if page > 50:
            break
        time.sleep(0.06)
    return all_fx, errors, last_status, error_body


def fetch_season_fixtures_list(sid, season_meta_row):
    """シーズンFixture一覧（診断情報付き）"""
    start = (season_meta_row.get("starting_at") or "")[:10]
    end = (season_meta_row.get("ending_at") or "")[:10]
    if not start:
        start = "2024-07-01"
    if not end:
        end = "2027-06-30"

    today = date.today().isoformat()
    wide_start = start
    wide_end = end if end > today else today
    if wide_end < wide_start:
        wide_end = wide_start

    methods_tried = []
    all_fx, errors, http_status, err_body = [], 0, None, None

    # A: fixtureSeasons
    fx_a, err_a, st_a, body_a = _paginate_fixtures(
        wide_start, wide_end, f"fixtureSeasons:{sid}"
    )
    methods_tried.append(
        {
            "method": "fixtureSeasons",
            "filter": f"fixtureSeasons:{sid}",
            "start": wide_start,
            "end": wide_end,
            "count": len(fx_a),
            "errors": err_a,
            "http": st_a,
            "error_body": body_a,
        }
    )
    all_fx, errors, http_status, err_body = fx_a, err_a, st_a, body_a

    # B: fixtureLeagues
    if len(all_fx) == 0:
        fx_b, err_b, st_b, body_b = _paginate_fixtures(
            wide_start, wide_end, f"fixtureLeagues:{LEAGUE_ID}"
        )
        methods_tried.append(
            {
                "method": "fixtureLeagues",
                "filter": f"fixtureLeagues:{LEAGUE_ID}",
                "start": wide_start,
                "end": wide_end,
                "count": len(fx_b),
                "errors": err_b,
                "http": st_b,
                "error_body": body_b,
            }
        )
        filtered = []
        for fx in fx_b:
            fx_sid = fx.get("season_id") or (fx.get("season") or {}).get("id")
            if fx_sid is None or int(fx_sid) == int(sid):
                filtered.append(fx)
        all_fx = filtered if filtered else fx_b
        errors += err_b
        http_status = st_b
        err_body = body_b

    # C: filterなし between → season_id でクライアント絞り込み
    if len(all_fx) == 0:
        fx_c, err_c, st_c, body_c = _paginate_fixtures(
            wide_start, wide_end, None
        )
        methods_tried.append(
            {
                "method": "between_no_filter",
                "filter": None,
                "start": wide_start,
                "end": wide_end,
                "count": len(fx_c),
                "errors": err_c,
                "http": st_c,
                "error_body": body_c,
            }
        )
        if fx_c:
            filtered = []
            for fx in fx_c:
                fx_sid = fx.get("season_id") or (fx.get("season") or {}).get("id")
                if fx_sid is not None and int(fx_sid) == int(sid):
                    filtered.append(fx)
            all_fx = filtered
        errors += err_c
        http_status = st_c
        err_body = body_c

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
        "start": wide_start,
        "end": wide_end,
        "season_meta_start": (season_meta_row.get("starting_at") or "")[:10],
        "season_meta_end": (season_meta_row.get("ending_at") or "")[:10],
        "total_fetched": len(all_fx),
        "finished_count": len(finished),
        "list_errors": errors,
        "http_status": http_status,
        "methods_tried": methods_tried,
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
    time.sleep(0.06)
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
        "fixtures": cached.get("fixtures") or cached.get("loaded_fixtures"),
        "players": len(restored),
        "new_fetched": cached.get("new_fetched", 0),
        "cached_fixtures": cached.get("cached_fixtures"),
        "finished_fixtures": cached.get("finished_fixtures"),
        "aggregate_rebuilt": cached.get("aggregate_rebuilt"),
        "updated_at": cached.get("updated_at"),
        "total_fetched": cached.get("total_fetched"),
        "from_cache_file": True,
        "mode": "cache_file",
        "errors": 0,
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
    total_fetched = flist.get("total_fetched", 0)

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
            status = {
                "finished_fixtures": finished_count,
                "cached_fixtures": len(cached_ids),
                "new_fetched": 0,
                "loaded_fixtures": len(loaded),
                "total_fetched": total_fetched,
                "errors": len(errors),
                "aggregate_rebuilt": False,
                "players": len(aggs),
                "updated_at": (meta or {}).get("updated_at") or now,
                "mode": "incremental_skip_rebuild",
                "season_id": sid,
                "methods_tried": flist.get("methods_tried"),
                "list_errors": flist.get("list_errors"),
                "season_meta_start": flist.get("season_meta_start"),
                "season_meta_end": flist.get("season_meta_end"),
            }
            return aggs, status, errors

    aggs = aggregate_player_team(loaded, sid)
    status = {
        "finished_fixtures": finished_count,
        "cached_fixtures": len(cached_ids),
        "new_fetched": new_fetched,
        "loaded_fixtures": len(loaded),
        "total_fetched": total_fetched,
        "errors": len(errors),
        "aggregate_rebuilt": True,
        "players": len(aggs),
        "fixtures": len(loaded),
        "mode": "rebuild",
        "season_id": sid,
        "updated_at": now,
        "methods_tried": flist.get("methods_tried"),
        "list_errors": flist.get("list_errors"),
        "season_meta_start": flist.get("season_meta_start"),
        "season_meta_end": flist.get("season_meta_end"),
    }
    save_aggs(sid, aggs, status)
    return aggs, status, errors


if st.session_state.get("fx_aggs") is None:
    with st.spinner(T["season_loading"]):
        aggs, meta = restore_aggs_from_file(season_id)
        if aggs is not None:
            st.session_state.fx_aggs = aggs
            st.session_state.fx_status = meta or {
                "from_cache_file": True,
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
errors = st.session_state.get("fx_errors") or []

updated_disp = format_updated_at(status.get("updated_at"))
st.caption(
    f"{T['connected']} · {T['last_updated']}: **{updated_disp}** · "
    f"Players: {status.get('players') or (len(aggs) if aggs else 0)} · "
    f"Season ID: {season_id}"
)

if not aggs:
    if (status.get("finished_fixtures") == 0):
        st.warning(T["no_fixtures"])
    else:
        st.info(T["no_data"])
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
        team_name = team_id_to_name.get(a["team_id"])
        if not team_name:
            team_name = str(a["team_id"]) if a["team_id"] is not None else "Unknown"
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
    cap = (
        f"n={n_total} · GK{len(by_pos['GK'])} / DEF{len(by_pos['DEF'])} / "
        f"MID{len(by_pos['MID'])} / FWD{len(by_pos['FWD'])}"
    )
    if float(min_min) >= 300:
        cap += f" · {T['early_note']}"
    st.caption(cap)

    if not all_players:
        st.warning(T["no_players"])
    else:
        all_players.sort(key=lambda g: (g["Player"] or "").lower())
        labels = [
            f"{g['Player']} · {g['Team']} · {g['Pos']} · {g['Minutes']}′"
            for g in all_players
        ]
        st.markdown(f"##### {T['player']}")
        choice = st.selectbox(T["player"], labels, label_visibility="collapsed")
        selected = all_players[labels.index(choice)]
        pos = selected["Pos"]
        mdefs = POSITION_METRICS[pos]
        n_pos = len(by_pos[pos])

        st.markdown(
            f"""
            <div style="border:1px solid #D7E0EC;border-radius:12px;padding:14px 16px;margin:8px 0 14px;background:#F8FAFC;">
              <div style="font-size:22px;font-weight:750;color:{NAVY};">{selected['Player']}</div>
              <div style="margin-top:6px;color:#334155;font-size:14px;">
                {selected['Team']} · <b>{pos}</b> · {selected['Minutes']} min · {T['apps']} {selected['Apps']}
              </div>
              <div style="margin-top:4px;color:#64748B;font-size:12px;">Superliga {season_name}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander(T["pct_title"], expanded=False):
            st.markdown(T["pct_body"])
            st.caption(T["band_legend"])

        st.markdown(f"##### {T['radar']}")
        radar_labels, radar_values, marker_colors, display_texts = [], [], [], []
        check_rows = []
        for m in mdefs:
            if m["kind"] in ("per90", "lower_better_per90"):
                raw_v = selected["raw"].get(m["tid"], 0)
            else:
                raw_v = (
                    f"{fmt_num(selected['raw'].get(m['num'], 0))} / "
                    f"{fmt_num(selected['raw'].get(m['den'], 0))}"
                )
            metric_v = selected["metrics"].get(m["key"])
            pct = selected.get("pct", {}).get(m["key"])
            band_name, band_color = percentile_band(pct)
            check_rows.append(
                {
                    "Metric": m["label"],
                    "Raw": raw_v if isinstance(raw_v, str) else fmt_num(raw_v, "raw"),
                    "Per90 / %": fmt_num(metric_v, "per90"),
                    "Percentile": fmt_num(pct, "pct"),
                    "Band": band_name,
                }
            )
            radar_labels.append(m["label"])
            radar_values.append(pct if pct is not None else 0)
            marker_colors.append(band_color)
            display_texts.append(
                fmt_radar_label(metric_v, is_ratio=(m["kind"] == "ratio"))
            )

        footnotes = [
            f"Shape = percentile (0–100) · Labels = Per90 (or %) · Sample: {pos}, ≥{int(min_min)} min (n={n_pos})",
            "Bands: Elite 90+ · Strong 70–89 · Average 30–69 · Below <30  |  Conceded/Fouls inverted",
            "Per90 uses Minutes Played · Pass Acc = Σ accurate ÷ Σ passes · Fixture aggregate",
            f"Superliga {season_name} · Superliga Radar · Data: Sportmonks API",
        ]

        fig = build_radar_figure(
            radar_labels,
            radar_values,
            [
                selected["Player"],
                f"{selected['Team']} | {pos} | {selected['Minutes']} min",
                f"Superliga {season_name} · Percentile radar",
            ],
            marker_colors,
            footnotes,
            display_texts,
        )
        try:
            png = fig.to_image(format="png", width=1200, height=1500, scale=2)
            st.image(png, use_container_width=True)
            st.caption(
                T["band_legend"]
                + (
                    " · Shape = percentile · Labels = Per90/%"
                    if is_en
                    else " · 形=Percentile · 数字=Per90/%"
                )
            )
            st.download_button(
                T["download"],
                data=png,
                file_name=f"{selected['Player'].replace(' ', '_')}_superliga_radar.png",
                mime="image/png",
            )
        except Exception as e:
            st.warning(str(e))

        st.markdown(f"##### {T['stats']}")
        df = pd.DataFrame(check_rows)
        st.dataframe(
            df.style.map(style_percentile_col, subset=["Percentile"]),
            use_container_width=True,
            hide_index=True,
        )

with st.expander(T["method_title"], expanded=False):
    if is_en:
        st.markdown(
            """
**Data source**
- Sportmonks Football API
- Danish Superliga (league 271)
- Fixture-level player statistics (`lineups.details`)

**Methodology**
- Minutes Played (type 119) as the Per90 denominator
- Per90 = total ÷ minutes × 90
- Pass accuracy = successful passes ÷ total passes
- Comparisons within the same position
- Percentile uses players above the selected minimum minutes
- Radar **shape** = percentile · vertex **labels** = Per90 (or %)
            """
        )
    else:
        st.markdown(
            """
**データソース**
- Sportmonks Football API
- デンマーク・スーペルリーガ（league 271）
- 試合単位の選手スタッツ（`lineups.details`）

**計算方法**
- 出場時間は Minutes Played（type 119）を分母に使用
- Per90 = 合計 ÷ 出場分 × 90
- パス成功率 = 成功パス合計 ÷ パス合計
- 比較は同じポジション内
- Percentileは最低出場時間以上の選手のみが母集団
- レーダーの**形** = Percentile · 頂点の**数字** = Per90（または%）
            """
        )

with st.expander(T["admin_title"], expanded=True):
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
            if status2.get("finished_fixtures", 0) == 0:
                st.warning(T["no_fixtures"])
            elif status2.get("aggregate_rebuilt"):
                st.success(
                    f"{T['rebuild_ok']} · new={status2.get('new_fetched', 0)} · "
                    f"players={status2.get('players', 0)}"
                )
            else:
                st.success(
                    f"{T['skip_ok']} · players={status2.get('players', 0)}"
                )
            st.rerun()

    st.markdown(f"**{T['status_title']}**")
    st.write(
        {
            "season_id": season_id,
            "season_meta_start": status.get("season_meta_start"),
            "season_meta_end": status.get("season_meta_end"),
            "finished_fixtures": status.get("finished_fixtures"),
            "total_fetched": status.get("total_fetched"),
            "cached_fixtures": status.get("cached_fixtures"),
            "new_fetched": status.get("new_fetched"),
            "loaded_fixtures": status.get("loaded_fixtures") or status.get("fixtures"),
            "aggregate_rebuilt": status.get("aggregate_rebuilt"),
            "players": status.get("players") or (len(aggs) if aggs else 0),
            "updated_at": status.get("updated_at"),
            "mode": status.get("mode"),
            "errors": status.get("errors")
            if status.get("errors") is not None
            else len(errors),
            "list_errors": status.get("list_errors"),
            "methods_tried": status.get("methods_tried"),
        }
    )
