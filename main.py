def build_radar_figure(labels, values, title_lines, marker_colors, footnotes):
    """
    - 上部タイトルの行間を広げて被り防止
    - チャート領域を大きく確保（画像は縦長）
    - 注釈は最下部
    """
    r_poly = values + [values[0]]
    theta = labels + [labels[0]]
    colors_closed = marker_colors + [marker_colors[0]]

    r_text = [min(v + 18, 118) for v in values]
    r_text_closed = r_text + [r_text[0]]
    text_vals = [f"{int(round(v))}" for v in values]
    text_closed = text_vals + [text_vals[0]]

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
                "size": 20,
                "line": {"color": NAVY, "width": 1.6},
            },
            mode="lines+markers",
            hovertemplate="%{theta}: %{r:.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=r_text_closed,
            theta=theta,
            mode="text",
            text=text_closed,
            textfont={
                "size": 28,
                "color": NAVY,
                "family": "Arial Black, Arial, sans-serif",
            },
            hoverinfo="skip",
        )
    )

    annotations = []
    # 行間を十分に取る（被り防止）
    # 0: 選手名 / 1: チーム・ポジション / 2: シーズン
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

    # 注釈は最下部（小さめ・左寄せ）
    foot_sizes = 13
    base_y = 0.105
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
                "font": {"color": "#4B5563", "size": foot_sizes, "family": "Arial"},
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
        # 縦長：チャートを大きく見せる
        height=1500,
        width=1000,
        margin={"l": 64, "r": 64, "t": 160, "b": 170},
        paper_bgcolor=WHITE,
        plot_bgcolor=WHITE,
        showlegend=False,
        images=images,
        annotations=annotations,
        polar={
            # 上部タイトル・下部注釈の間でチャートを最大化
            "domain": {"x": [0.04, 0.96], "y": [0.16, 0.82]},
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
                    "size": 24,
                    "family": "Arial Black, Arial, sans-serif",
                },
                "rotation": 90,
                "direction": "clockwise",
            },
        },
    )
    return fig
