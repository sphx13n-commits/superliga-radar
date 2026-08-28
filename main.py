import base64
import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Superliga Radar",
    page_icon="⚽",
    layout="centered",
)

components.html(
    """
    <script>
    (function () {
      try {
        if (window.parent && window.parent.history) {
          window.parent.history.scrollRestoration = 'manual';
        }
      } catch (e) {}
      function toTop() {
        try {
          const doc = window.parent.document;
          const main = doc.querySelector('section.main') || doc.scrollingElement || doc.body;
          if (main && main.scrollTo) main.scrollTo(0, 0);
          if (window.parent.scrollTo) window.parent.scrollTo(0, 0);
        } catch (e) {}
      }
      toTop();
      setTimeout(toTop, 50);
      setTimeout(toTop, 200);
    })();
    </script>
    """,
    height=0,
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
POSITIONS = ("GK", "DEF", "MID", "FWD")
MAX_BETWEEN_DAYS = 90
MAX_SEASONS = 3
SMALL_SAMPLE_N = 15
PCT_THRESHOLDS = [50, 60, 70, 80, 90]

BAND_ELITE = "#0B1F3A"
BAND_STRONG = "#2563EB"
BAND_AVG = "#64748B"
BAND_BELOW = "#CBD5E1"


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


def short_name(name, n=14):
    if not name:
        return "—"
    name = str(name)
    return name if len(name) <= n else name[: n - 1] + "…"


def calc_age(dob_str, as_of):
    if not dob_str or as_of is None:
        return None
    try:
        dob = datetime.strptime(str(dob_str)[:10], "%Y-%m-%d").date()
        age = as_of.year - dob.year
        if (as_of.month, as_of.day) < (dob.month, dob.day):
            age -= 1
        if age < 0 or age > 60:
            return None
        return int(age)
    except Exception:
        return None


def fmt_age(age):
    return "—" if age is None else str(int(age))


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
    "min_minutes": "Minimum minutes" if is_en else "最低出場時間",
    "team": "Team" if is_en else "チーム",
    "all_teams": "All teams" if is_en else "すべてのチーム",
    "player": "Player" if is_en else "選手",
    "position": "Position" if is_en else "ポジション",
    "player_a": "Player A" if is_en else "選手 A",
    "player_b": "Player B" if is_en else "選手 B",
    "team_a": "Team A" if is_en else "チーム A",
    "team_b": "Team B" if is_en else "チーム B",
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
        "Bands: Elite 90+ · Strong 70–89 · Average 30–69 · Below <30"
        if is_en
        else "同ポジション・出場時間条件での順位（0–100）。\n\n"
        "帯: Elite 90+ · Strong 70–89 · Average 30–69 · Below 30未満"
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
        "Vertex (single): Elite 90+ · Strong 70–89 · Average 30–69 · Below <30"
        if is_en
        else "頂点色（単体）: Elite 90+ · Strong 70–89 · Average 30–69 · Below 30未満"
    ),
    "method_title": "Data & methodology" if is_en else "データと計算方法",
    "admin_title": "Data maintenance" if is_en else "データメンテナンス",
    "last_updated": "Last updated" if is_en else "最終更新",
    "connected": "Connected" if is_en else "接続済み",
    "apps": "Apps" if is_en else "出場数",
    "season_loading": "Loading..." if is_en else "読み込み中...",
    "discover_hint": (
        "Enable metrics and set a minimum percentile. Same pool as Radar."
        if is_en
        else "指標を有効化し、最低Percentileを設定。母集団はRadarと同じです。"
    ),
    "metric_filters": "Metric filters" if is_en else "指標フィルタ",
    "results": "Results" if is_en else "検索結果",
    "no_results": "No players match the filters." if is_en else "条件に合う選手がいません。",
    "min_pct": "Min %ile" if is_en else "最低%ile",
    "tab_radar": "⚽ Player Radar" if is_en else "⚽ 選手レーダー",
    "tab_compare": "⚔️ Compare" if is_en else "⚔️ 選手比較",
    "tab_discover": "🔍 Discover" if is_en else "🔍 探索",
    "tab_similar": "👥 Similar" if is_en else "👥 類似選手",
    "similar_hint": (
        "Find same-position players with a similar percentile profile (radar shape)."
        if is_en
        else "同ポジションで Percentile の形が近い選手を探します。"
    ),
    "ref_player": "Reference player" if is_en else "基準選手",
    "top_n": "Show top" if is_en else "表示件数",
    "similarity": "Similarity" if is_en else "類似度",
    "no_similar": "Not enough players to compare." if is_en else "比較できる選手が足りません。",
    "age": "Age" if is_en else "年齢",
    "ages_loading": "Loading player ages..." if is_en else "年齢データを取得中...",
    "png_fallback": (
        "PNG export is unavailable right now. Showing interactive chart instead."
        if is_en
        else "PNG書き出しが使えないため、画面上のチャートのみ表示しています。"
    ),
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


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_image_data_uri(url: str):
    if not url or not isinstance(url, str):
        return None
    try:
        r = requests.get(url, timeout=12)
        if r.status_code != 200 or not r.content:
            return None
        ctype = (r.headers.get("Content-Type") or "image/png").split(";")[0].strip()
        if "png" in ctype:
            mime = "image/png"
        elif "jpeg" in ctype or "jpg" in ctype:
            mime = "image/jpeg"
        elif "svg" in ctype:
            mime = "image/svg+xml"
        else:
            mime = "image/png"
        b64 = base64.b64encode(r.content).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None


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


def as_of_date_from_status(status_obj):
    iso = (status_obj or {}).get("updated_at")
    if iso:
        try:
            s = str(iso).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt.date()
        except Exception:
            pass
    return date.today()


def players_meta_path():
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    return CACHE_ROOT / "players_meta.json"


def load_players_meta():
    data = _load_json(players_meta_path())
    return data if isinstance(data, dict) else {}


def save_players_meta(meta):
    _save_json(players_meta_path(), meta)


def fetch_player_dob(player_id):
    try:
        res = requests.get(
            f"{base_url}/players/{player_id}",
            headers=headers,
            params=params,
            timeout=20,
        )
        if res.status_code != 200:
            return None
        data = (res.json() or {}).get("data") or {}
        dob = data.get("date_of_birth") or data.get("birthday") or data.get("birthdate")
        return str(dob)[:10] if dob else None
    except Exception:
        return None


class nullcontext:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def ensure_player_ages(aggs, show_spinner=True):
    meta = load_players_meta()
    needed = set()
    for a in (aggs or {}).values():
        pid = a.get("player_id")
        if pid is None:
            continue
        key = str(pid)
        if key not in meta or not (meta[key] or {}).get("dob"):
            needed.add(int(pid))

    if not needed:
        return meta

    spinner_ctx = st.spinner(T["ages_loading"]) if show_spinner else nullcontext()
    with spinner_ctx:
        for i, pid in enumerate(sorted(needed)):
            dob = fetch_player_dob(pid)
            meta[str(pid)] = {
                "dob": dob,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            if (i + 1) % 20 == 0:
                save_players_meta(meta)
            time.sleep(0.05)
        save_players_meta(meta)
    return meta


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
    marker_colors_a=None,
    club_logo_uri=None,
):
    fig = go.Figure()
    n = len(labels)
    theta = labels + [labels[0]]

    if marker_colors_a and values_b is None:
        m_colors = list(marker_colors_a) + [marker_colors_a[0]]
    else:
        m_colors = NAVY

    r_a = values_a + [values_a[0]]
    fig.add_trace(
        go.Scatterpolar(
            r=r_a,
            theta=theta,
            fill="toself",
            fillcolor=NAVY_SOFT,
            line={"color": NAVY, "width": 3.4},
            marker={
                "color": m_colors,
                "size": 16,
                "line": {"color": NAVY, "width": 1.8},
            },
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
                    "size": 16,
                    "line": {"color": WHITE, "width": 1.2},
                },
                mode="lines+markers",
                name=name_b or "B",
                hovertemplate="%{theta}: %{r:.0f}<extra>" + (name_b or "B") + "</extra>",
            )
        )

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
    if values_b is not None:
        title_sizes = [32, 18, 14]
        title_ys = [0.975, 0.935, 0.905]
    else:
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

    base_y = 0.118 if values_b is None else 0.108
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
                "font": {"color": "#374151", "size": 13, "family": "Arial"},
            }
        )

    annotations.append(
        {
            "text": "<b>@Dalaprospect</b>",
            "xref": "paper",
            "yref": "paper",
            "x": 0.97,
            "y": 0.012,
            "xanchor": "right",
            "yanchor": "bottom",
            "showarrow": False,
            "font": {"color": NAVY, "size": 14, "family": "Arial"},
        }
    )

    images = []
    if club_logo_uri and values_b is None:
        images.append(
            {
                "source": club_logo_uri,
                "xref": "paper",
                "yref": "paper",
                "x": 0.03,
                "y": 0.97,
                "sizex": 0.13,
                "sizey": 0.13,
                "xanchor": "left",
                "yanchor": "top",
                "sizing": "contain",
                "layer": "above",
            }
        )

    brand = get_logo_data_uri()
    if brand:
        images.append(
            {
                "source": brand,
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
        color, text = "#2563EB", "#FFFFFF"
    elif p >= 30:
        color, text = "#64748B", "#FFFFFF"
    else:
        color, text = "#E2E8F0", NAVY
    return f"background-color: {color}; color: {text}; font-weight: 700;"


def player_key(g):
    return f"{g.get('Player')}|{g.get('Team')}|{g.get('Pos')}|{g.get('Minutes')}"


def pct_vector(g, mdefs):
    vec = []
    for m in mdefs:
        p = g.get("pct", {}).get(m["key"])
        vec.append(50.0 if p is None else float(p))
    return vec


def similarity_score(vec_a, vec_b):
    if not vec_a or len(vec_a) != len(vec_b):
        return 0.0
    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))
    max_dist = 100.0 * math.sqrt(len(vec_a))
    if max_dist <= 0:
        return 100.0
    return round(max(0.0, 100.0 * (1.0 - dist / max_dist)), 1)


def build_position_pools(aggs, team_id_to_name, min_min, players_meta=None, as_of=None):
    players_meta = players_meta or {}
    as_of = as_of or date.today()
    by_pos = {p: [] for p in POSITIONS}
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
        pid = a.get("player_id")
        dob = None
        if pid is not None:
            dob = (players_meta.get(str(pid)) or {}).get("dob")
        age = calc_age(dob, as_of)
        by_pos[pos].append(
            {
                "Player": a["player_name"] or f"id:{a['player_id']}",
                "PlayerId": pid,
                "Team": team_name,
                "TeamId": a["team_id"],
                "Pos": pos,
                "Minutes": int(round(mins)),
                "Apps": a["apps"],
                "Age": age,
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
    return by_pos


def get_pools_cached(season_id, min_min, aggs, team_id_to_name, players_meta, as_of):
    key = f"pools_{season_id}_{int(min_min)}_{as_of.isoformat()}"
    if st.session_state.get("_pools_key") != key or "pools_data" not in st.session_state:
        st.session_state["_pools_key"] = key
        st.session_state["pools_data"] = build_position_pools(
            aggs, team_id_to_name, min_min, players_meta, as_of
        )
    return st.session_state["pools_data"]


def render_png(fig, fname_base):
    try:
        png = fig.to_image(format="png", width=1200, height=1500, scale=2)
        st.image(png, use_container_width=True)
        st.download_button(
            T["download"],
            data=png,
            file_name=f"{fname_base}_superliga_radar.png",
            mime="image/png",
        )
        return True
    except Exception:
        st.plotly_chart(fig, use_container_width=True)
        st.caption(T["png_fallback"])
        return False


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
    st.session_state.pop("pools_data", None)
    st.session_state.pop("_pools_key", None)
    for k in list(st.session_state.keys()):
        if k.startswith(("player_", "disc_", "cmp_", "radar_", "sim_")):
            del st.session_state[k]

teams_res = requests.get(
    f"{base_url}/teams/seasons/{season_id}",
    headers=headers,
    params=params,
    timeout=30,
)
teams = teams_res.json().get("data", []) if teams_res.status_code == 200 else []
team_id_to_name = {}
team_id_to_logo = {}
for t in teams:
    tid = t.get("id")
    if tid is None:
        continue
    team_id_to_name[tid] = t.get("name") or str(tid)
    logo = t.get("image_path") or t.get("logo_path") or t.get("image")
    if logo:
        team_id_to_logo[tid] = logo


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

    fx_a, err_a, _, _, _ = _fetch_between_chunked(
        wide_start, wide_end, f"fixtureSeasons:{sid}"
    )
    all_fx, errors = fx_a, err_a

    if len(all_fx) == 0:
        fx_b, err_b, _, _, _ = _fetch_between_chunked(
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
as_of = as_of_date_from_status(status)

st.caption(
    f"{T['connected']} · {T['last_updated']}: **{format_updated_at(status.get('updated_at'))}** · "
    f"Players: {status.get('players') or (len(aggs) if aggs else 0)} · Season ID: {season_id}"
)

if not aggs:
    st.warning(T["no_fixtures"] if status.get("finished_fixtures") == 0 else T["no_data"])
    st.stop()

players_meta = ensure_player_ages(aggs, show_spinner=True)

tab_radar, tab_compare, tab_discover, tab_similar = st.tabs(
    [T["tab_radar"], T["tab_compare"], T["tab_discover"], T["tab_similar"]]
)

# -------------------- RADAR --------------------
with tab_radar:
    f1, f2 = st.columns(2)
    with f1:
        min_min_r = st.selectbox(
            T["min_minutes"], [0, 300, 600, 900], index=1, key="radar_min"
        )
    by_pos_r = get_pools_cached(
        season_id, min_min_r, aggs, team_id_to_name, players_meta, as_of
    )
    all_r = [g for pos in by_pos_r.values() for g in pos]
    teams_r = sorted({str(g["Team"]) for g in all_r if g.get("Team")})
    with f2:
        team_r = st.selectbox(
            T["team"], [T["all_teams"]] + teams_r, key="radar_team"
        )
    if team_r != T["all_teams"]:
        all_r = [g for g in all_r if g["Team"] == team_r]

    n_total = sum(len(v) for v in by_pos_r.values())
    n_by = {p: len(by_pos_r[p]) for p in POSITIONS}
    st.caption(
        f"n={n_total} · GK{n_by['GK']} / DEF{n_by['DEF']} / MID{n_by['MID']} / FWD{n_by['FWD']}"
    )
    if 0 < n_total < 40:
        st.info(T["early_note"])

    if not all_r:
        st.warning(T["no_players"])
    else:
        all_r.sort(key=lambda g: (g["Player"] or "").lower())
        labels_r = [
            f"{g['Player']} · {g['Team']} · {g['Pos']} · {g['Minutes']}′" for g in all_r
        ]
        st.markdown(f"##### {T['player']}")
        choice_r = st.selectbox(
            T["player"], labels_r, key="player_radar", label_visibility="collapsed"
        )
        sel = all_r[labels_r.index(choice_r)]
        pos = sel["Pos"]
        mdefs = POSITION_METRICS[pos]
        n_pos = len(by_pos_r[pos])
        is_small = n_pos < SMALL_SAMPLE_N
        age_str = fmt_age(sel.get("Age"))

        club_uri = None
        url = team_id_to_logo.get(sel.get("TeamId"))
        if url:
            club_uri = fetch_image_data_uri(url)

        logo_html = (
            f'<img src="{club_uri}" style="height:40px;width:40px;object-fit:contain;margin-right:10px;vertical-align:middle;" />'
            if club_uri
            else ""
        )
        st.markdown(
            f"""
            <div style="border:1px solid #D7E0EC;border-radius:12px;padding:14px 16px;margin:8px 0 14px;background:#F8FAFC;display:flex;align-items:center;">
              {logo_html}
              <div>
                <div style="font-size:22px;font-weight:750;color:{NAVY};">{sel['Player']}</div>
                <div style="margin-top:6px;color:#334155;font-size:14px;">
                  {sel['Team']} · <b>{pos}</b> · {age_str} · {sel['Minutes']} min · {T['apps']} {sel['Apps']}
                </div>
                <div style="margin-top:4px;color:#64748B;font-size:12px;">Superliga {season_name}</div>
              </div>
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
        values_a = [sel.get("pct", {}).get(m["key"]) or 0 for m in mdefs]
        display_a = [
            fmt_radar_label(sel["metrics"].get(m["key"]), is_ratio=(m["kind"] == "ratio"))
            for m in mdefs
        ]
        marker_colors_a = [
            percentile_band(sel.get("pct", {}).get(m["key"]))[1] for m in mdefs
        ]
        sample_line = f"{pos}, ≥{int(min_min_r)}′ (n={n_pos})"
        if is_small:
            sample_line += " · ⚠ small" if is_en else " · ⚠ 母集団小"

        footnotes = [
            f"Shape = percentile · Vertex = band · Ring = 100 · {sample_line}",
            "Bands: Elite 90+ · Strong 70–89 · Average 30–69 · Below <30",
            "Per90 = Minutes Played · Fixture aggregate · Sportmonks",
            f"Superliga {season_name} · Superliga Radar · @Dalaprospect",
        ]
        title_lines = [
            sel["Player"],
            f"{sel['Team']} | {pos} | {age_str} | {sel['Minutes']} min",
            f"Superliga {season_name} · Percentile radar",
        ]
        fig = build_radar_figure(
            radar_labels,
            values_a,
            title_lines,
            footnotes,
            display_texts=display_a,
            name_a=sel["Player"],
            marker_colors_a=marker_colors_a,
            club_logo_uri=club_uri,
        )
        st.caption(T["band_legend"])
        render_png(fig, sel["Player"].replace(" ", "_"))

        st.markdown(f"##### {T['stats']}")
        na = short_name(sel["Player"])
        rows = []
        for m in mdefs:
            raw_v = (
                sel["raw"].get(m["tid"], 0)
                if m["kind"] in ("per90", "lower_better_per90")
                else (
                    f"{fmt_num(sel['raw'].get(m['num'], 0))} / "
                    f"{fmt_num(sel['raw'].get(m['den'], 0))}"
                )
            )
            rows.append(
                {
                    "Metric": m["label"],
                    f"{na} Per90/%": fmt_num(sel["metrics"].get(m["key"]), "per90"),
                    f"{na} %ile": fmt_num(sel.get("pct", {}).get(m["key"]), "pct"),
                    "Raw": raw_v if isinstance(raw_v, str) else fmt_num(raw_v, "raw"),
                    "Band": percentile_band(sel.get("pct", {}).get(m["key"]))[0],
                }
            )
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

# -------------------- COMPARE --------------------
with tab_compare:
    c1, c2 = st.columns(2)
    with c1:
        min_min_c = st.selectbox(
            T["min_minutes"], [0, 300, 600, 900], index=1, key="cmp_min"
        )
    with c2:
        pos_c = st.selectbox(T["position"], list(POSITIONS), index=2, key="cmp_pos")

    by_pos_c = get_pools_cached(
        season_id, min_min_c, aggs, team_id_to_name, players_meta, as_of
    )
    pool = by_pos_c[pos_c]
    n_pos = len(pool)
    if 0 < n_pos < SMALL_SAMPLE_N:
        st.warning(T["small_sample"].format(n=n_pos))

    teams_in_pos = sorted({str(g["Team"]) for g in pool if g.get("Team")})
    if len(pool) < 2:
        st.warning(T["no_compare"])
    else:
        a_col, b_col = st.columns(2)
        with a_col:
            team_a = st.selectbox(
                T["team_a"], [T["all_teams"]] + teams_in_pos, key="cmp_team_a"
            )
            pool_a = (
                pool
                if team_a == T["all_teams"]
                else [g for g in pool if g["Team"] == team_a]
            )
            pool_a = sorted(pool_a, key=lambda g: (g["Player"] or "").lower())
            labels_a = [
                f"{g['Player']} · {g['Team']} · {g['Minutes']}′" for g in pool_a
            ]
            if not labels_a:
                st.warning(T["no_players"])
                sel_a = None
            else:
                choice_a = st.selectbox(T["player_a"], labels_a, key="cmp_player_a")
                sel_a = pool_a[labels_a.index(choice_a)]

        with b_col:
            team_b = st.selectbox(
                T["team_b"], [T["all_teams"]] + teams_in_pos, key="cmp_team_b"
            )
            pool_b = (
                pool
                if team_b == T["all_teams"]
                else [g for g in pool if g["Team"] == team_b]
            )
            pool_b = sorted(pool_b, key=lambda g: (g["Player"] or "").lower())
            labels_b = [
                f"{g['Player']} · {g['Team']} · {g['Minutes']}′" for g in pool_b
            ]
            if not labels_b:
                st.warning(T["no_players"])
                sel_b = None
            else:
                choice_b = st.selectbox(T["player_b"], labels_b, key="cmp_player_b")
                sel_b = pool_b[labels_b.index(choice_b)]

        if sel_a is not None and sel_b is not None:
            if player_key(sel_a) == player_key(sel_b):
                st.info(
                    "Select two different players."
                    if is_en
                    else "別の選手を選んでください。"
                )
            else:
                mdefs = POSITION_METRICS[pos_c]
                radar_labels = [m["label"] for m in mdefs]
                values_a = [sel_a.get("pct", {}).get(m["key"]) or 0 for m in mdefs]
                values_b = [sel_b.get("pct", {}).get(m["key"]) or 0 for m in mdefs]
                sample_line = f"{pos_c}, ≥{int(min_min_c)}′ (n={n_pos})"
                footnotes = [
                    f"Overlay = percentile · Ring = 100 · {sample_line}",
                    f"Navy = {sel_a['Player']} · Orange = {sel_b['Player']}",
                    "Same position only · Numbers in table below",
                    f"Superliga {season_name} · Superliga Radar · @Dalaprospect",
                ]
                title_lines = [
                    f"{sel_a['Player']}  vs  {sel_b['Player']}",
                    f"{pos_c} · Superliga {season_name}",
                    "Percentile comparison",
                ]
                st.markdown(f"##### {T['radar']}")
                fig = build_radar_figure(
                    radar_labels,
                    values_a,
                    title_lines,
                    footnotes,
                    display_texts=None,
                    values_b=values_b,
                    name_a=sel_a["Player"],
                    name_b=sel_b["Player"],
                    marker_colors_a=None,
                    club_logo_uri=None,
                )
                render_png(
                    fig,
                    f"{sel_a['Player'].replace(' ', '_')}_vs_{sel_b['Player'].replace(' ', '_')}",
                )

                st.markdown(f"##### {T['stats']}")
                na, nb = short_name(sel_a["Player"]), short_name(sel_b["Player"])
                rows = []
                for m in mdefs:
                    rows.append(
                        {
                            "Metric": m["label"],
                            f"{na} Per90/%": fmt_num(
                                sel_a["metrics"].get(m["key"]), "per90"
                            ),
                            f"{na} %ile": fmt_num(
                                sel_a.get("pct", {}).get(m["key"]), "pct"
                            ),
                            f"{nb} Per90/%": fmt_num(
                                sel_b["metrics"].get(m["key"]), "per90"
                            ),
                            f"{nb} %ile": fmt_num(
                                sel_b.get("pct", {}).get(m["key"]), "pct"
                            ),
                        }
                    )
                df = pd.DataFrame(rows)
                pct_cols = [c for c in df.columns if "%ile" in c]
                st.dataframe(
                    df.style.map(style_percentile_col, subset=pct_cols),
                    use_container_width=True,
                    hide_index=True,
                )

# -------------------- DISCOVER --------------------
with tab_discover:
    st.caption(T["discover_hint"])
    d1, d2, d3 = st.columns(3)
    with d1:
        pos_d = st.selectbox(T["position"], list(POSITIONS), index=2, key="disc_pos")
    with d2:
        min_min_d = st.selectbox(
            T["min_minutes"], [0, 300, 600, 900], index=1, key="disc_min"
        )
    by_pos_d = get_pools_cached(
        season_id, min_min_d, aggs, team_id_to_name, players_meta, as_of
    )
    pool_d = by_pos_d[pos_d]
    teams_d = sorted({str(g["Team"]) for g in pool_d if g.get("Team")})
    with d3:
        team_d = st.selectbox(
            T["team"], [T["all_teams"]] + teams_d, key="disc_team"
        )
    if team_d != T["all_teams"]:
        pool_d = [g for g in pool_d if g["Team"] == team_d]

    n_pos = len(by_pos_d[pos_d])
    if 0 < n_pos < SMALL_SAMPLE_N:
        st.warning(T["small_sample"].format(n=n_pos))

    mdefs = POSITION_METRICS[pos_d]
    st.markdown(f"##### {T['metric_filters']}")
    active_filters = []
    for m in mdefs:
        cols = st.columns([2, 1, 2])
        with cols[0]:
            use = st.checkbox(m["label"], value=False, key=f"disc_use_{m['key']}")
        with cols[1]:
            st.caption(T["min_pct"] if use else "")
        with cols[2]:
            if use:
                thr = st.selectbox(
                    T["min_pct"],
                    PCT_THRESHOLDS,
                    index=2,
                    key=f"disc_thr_{m['key']}",
                    label_visibility="collapsed",
                )
                active_filters.append((m, thr))
            else:
                st.write("")

    st.markdown(f"##### {T['results']}")
    if not active_filters:
        st.info(
            "Enable at least one metric filter."
            if is_en
            else "1つ以上の指標フィルタを有効にしてください。"
        )
    else:
        results = []
        for g in pool_d:
            ok = True
            for m, thr in active_filters:
                p = g.get("pct", {}).get(m["key"])
                if p is None or p < thr:
                    ok = False
                    break
            if ok:
                results.append(g)

        if not results:
            st.warning(T["no_results"])
        else:
            sort_key = active_filters[0][0]["key"]
            results.sort(
                key=lambda g: g.get("pct", {}).get(sort_key) or 0, reverse=True
            )
            rows = []
            for g in results:
                row = {
                    "Player": g["Player"],
                    "Team": g["Team"],
                    T["age"]: fmt_age(g.get("Age")),
                    "Pos": g["Pos"],
                    "Minutes": g["Minutes"],
                }
                for m, _thr in active_filters:
                    row[m["label"]] = fmt_num(g["metrics"].get(m["key"]), "per90")
                    row[f"{m['label']} %ile"] = fmt_num(
                        g.get("pct", {}).get(m["key"]), "pct"
                    )
                rows.append(row)
            df = pd.DataFrame(rows)
            pct_cols = [c for c in df.columns if "%ile" in c]
            st.caption(f"{len(results)} players")
            if pct_cols:
                st.dataframe(
                    df.style.map(style_percentile_col, subset=pct_cols),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(
                "Open Player Radar tab to view the full radar."
                if is_en
                else "詳細は 選手レーダー タブで選手を選んで確認できます。"
            )

# -------------------- SIMILAR PLAYERS --------------------
with tab_similar:
    st.caption(T["similar_hint"])
    s1, s2, s3 = st.columns(3)
    with s1:
        pos_s = st.selectbox(T["position"], list(POSITIONS), index=2, key="sim_pos")
    with s2:
        min_min_s = st.selectbox(
            T["min_minutes"], [0, 300, 600, 900], index=1, key="sim_min"
        )
    by_pos_s = get_pools_cached(
        season_id, min_min_s, aggs, team_id_to_name, players_meta, as_of
    )
    pool_s = by_pos_s[pos_s]
    teams_s = sorted({str(g["Team"]) for g in pool_s if g.get("Team")})
    with s3:
        team_s = st.selectbox(
            T["team"], [T["all_teams"]] + teams_s, key="sim_team"
        )

    pool_ref = (
        pool_s if team_s == T["all_teams"] else [g for g in pool_s if g["Team"] == team_s]
    )
    pool_ref = sorted(pool_ref, key=lambda g: (g["Player"] or "").lower())
    n_pos = len(pool_s)
    if 0 < n_pos < SMALL_SAMPLE_N:
        st.warning(T["small_sample"].format(n=n_pos))

    if len(pool_s) < 2 or not pool_ref:
        st.warning(T["no_similar"])
    else:
        labels_ref = [
            f"{g['Player']} · {g['Team']} · {g['Minutes']}′" for g in pool_ref
        ]
        choice_ref = st.selectbox(T["ref_player"], labels_ref, key="sim_ref")
        ref = pool_ref[labels_ref.index(choice_ref)]
        top_n = st.selectbox(T["top_n"], [5, 10, 15], index=1, key="sim_topn")

        mdefs = POSITION_METRICS[pos_s]
        ref_vec = pct_vector(ref, mdefs)

        scored = []
        for g in pool_s:
            if player_key(g) == player_key(ref):
                continue
            sim = similarity_score(ref_vec, pct_vector(g, mdefs))
            scored.append((sim, g))
        scored.sort(key=lambda x: x[0], reverse=True)
        scored = scored[: int(top_n)]

        st.markdown(f"##### {T['results']}")
        if not scored:
            st.warning(T["no_similar"])
        else:
            rows = []
            ref_row = {
                "#": "★",
                "Player": ref["Player"],
                "Team": ref["Team"],
                T["age"]: fmt_age(ref.get("Age")),
                "Minutes": ref["Minutes"],
                T["similarity"]: fmt_num(100, "pct"),
            }
            for m in mdefs[:4]:
                ref_row[f"{m['label']} %ile"] = fmt_num(
                    ref.get("pct", {}).get(m["key"]), "pct"
                )
            rows.append(ref_row)

            for rank, (sim, g) in enumerate(scored, start=1):
                row = {
                    "#": rank,
                    "Player": g["Player"],
                    "Team": g["Team"],
                    T["age"]: fmt_age(g.get("Age")),
                    "Minutes": g["Minutes"],
                    T["similarity"]: fmt_num(sim, "pct"),
                }
                for m in mdefs[:4]:
                    row[f"{m['label']} %ile"] = fmt_num(
                        g.get("pct", {}).get(m["key"]), "pct"
                    )
                rows.append(row)

            df = pd.DataFrame(rows)
            pct_cols = [c for c in df.columns if "%ile" in c]
            st.caption(
                f"{ref['Player']} · {pos_s} · n={n_pos}"
                + (
                    " · ★ = reference · similarity from percentile shape"
                    if is_en
                    else " · ★ = 基準選手 · Percentile形状に基づく類似度"
                )
            )
            if pct_cols:
                st.dataframe(
                    df.style.map(style_percentile_col, subset=pct_cols),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(
                "Open Compare or Player Radar to inspect profiles."
                if is_en
                else "詳細は 選手比較 または 選手レーダー タブで確認できます。"
            )

with st.expander(T["method_title"], expanded=False):
    st.markdown(
        "形=Percentile · 類似度=同ポジションのPercentileベクトル距離 · 年齢=データ抽出日時点"
        if not is_en
        else "Shape=percentile · Similarity=percentile-vector distance · Age=as of data extract date"
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
            st.session_state.pop("pools_data", None)
            st.session_state.pop("_pools_key", None)
            st.rerun()
    st.write(
        {
            "season_id": season_id,
            "players": status.get("players") or (len(aggs) if aggs else 0),
            "updated_at": status.get("updated_at"),
            "mode": status.get("mode"),
            "age_as_of": as_of.isoformat(),
        }
    )
