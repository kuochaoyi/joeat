"""揪呷 JOEAT — Python Dash 營運數據分析儀表板，掛載於 FastAPI /ops/dash/。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from dash import Dash, Input, Output, dcc, html
import plotly.graph_objects as go
from sqlalchemy import text

from app.db.session import get_engine

# 品牌色票（與前端 Tailwind 暖橘風格一致）
BRAND = "#ff6b35"
BRAND_LIGHT = "#ff944d"
BG = "#fffbf7"
CARD_BG = "#ffffff"
INK = "#1e293b"
MUTED = "#64748b"
LINE = "#eadfd5"
OK = "#059669"
WARN = "#d97706"
CRIT = "#dc2626"
BLUE = "#2563eb"

DECL_STATUS_ZH = {
    "submitted": "待審核",
    "approved": "已核准",
    "needs_info": "退回補件",
    "rejected": "已駁回",
    "withdrawn": "已撤下",
    "draft": "草稿",
}

POOL_STATUS_ZH = {
    "active": "正式候選池",
    "candidate": "待審候選",
    "excluded": "已排除",
    "inactive": "停用／歇業",
}

ISSUE_KIND_ZH = {
    "allergic_reaction": "過敏反應",
    "wrong_info": "資訊有誤",
    "closed": "歇業／搬遷",
    "other": "其他",
}


def _fetch_analytics(include_demo: bool) -> dict[str, Any]:
    """從 PostgreSQL 彙整營運與推薦統計數據。"""
    demo_clause = "" if include_demo else "AND c.is_demo = false"
    with get_engine().connect() as conn:
        kpi = conn.execute(text(
            "SELECT "
            "  (SELECT count(*) FROM identity.restaurant WHERE merged_into_restaurant_id IS NULL) AS restaurants, "
            f"  (SELECT count(DISTINCT d.restaurant_id) FROM merchant.declaration d JOIN merchant.claim c USING (claim_id) WHERE d.status = 'approved' {demo_clause}) AS verified_restaurants, "
            "  (SELECT count(*) FROM product.dining_session) AS sessions, "
            "  (SELECT count(*) FROM product.participant) AS participants, "
            "  (SELECT count(*) FROM merchant.incident_report WHERE status = 'open') AS open_incidents"
        )).mappings().one()

        decl_rows = conn.execute(text(
            "SELECT d.status, count(*) AS cnt "
            "FROM merchant.declaration d JOIN merchant.claim c USING (claim_id) "
            f"WHERE 1=1 {demo_clause} "
            "GROUP BY d.status ORDER BY cnt DESC"
        )).mappings().all()

        pool_rows = conn.execute(text(
            "SELECT pool_status, count(*) AS cnt "
            "FROM identity.restaurant WHERE merged_into_restaurant_id IS NULL "
            "GROUP BY pool_status ORDER BY cnt DESC"
        )).mappings().all()

        report_rows = conn.execute(text(
            "SELECT kind, count(*) AS cnt FROM product.restaurant_report GROUP BY kind"
        )).mappings().all()

        incident_rows = conn.execute(text(
            "SELECT severity AS kind, count(*) AS cnt FROM merchant.incident_report GROUP BY severity"
        )).mappings().all()

        session_trend = conn.execute(text(
            "SELECT to_char(date_trunc('day', s.created_at AT TIME ZONE 'Asia/Taipei'), 'YYYY-MM-DD') AS day, "
            "       count(DISTINCT s.session_id) AS session_cnt, "
            "       count(p.participant_id) AS participant_cnt "
            "FROM product.dining_session s "
            "LEFT JOIN product.participant p ON p.session_id = s.session_id "
            "GROUP BY 1 ORDER BY 1 DESC LIMIT 14"
        )).mappings().all()

    return {
        "kpi": {k: int(v or 0) for k, v in kpi.items()},
        "decl": [(r["status"], int(r["cnt"])) for r in decl_rows],
        "pool": [(r["pool_status"], int(r["cnt"])) for r in pool_rows],
        "reports": {r["kind"]: int(r["cnt"]) for r in report_rows},
        "incidents": {r["kind"]: int(r["cnt"]) for r in incident_rows},
        "trend": list(reversed([dict(r) for r in session_trend])),
    }


def _empty_figure(title: str, note: str = "目前尚無資料") -> go.Figure:
    """無資料時顯示友善提示的空白圖表。"""
    fig = go.Figure()
    fig.add_annotation(
        text=note,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 14, "color": MUTED},
    )
    fig.update_layout(
        title={"text": title, "font": {"size": 15, "color": INK}},
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        xaxis={"visible": False},
        yaxis={"visible": False},
        margin={"l": 24, "r": 24, "t": 48, "b": 24},
        height=300,
    )
    return fig


def _base_layout(title: str) -> dict[str, Any]:
    return {
        "title": {"text": title, "font": {"size": 15, "color": INK}},
        "paper_bgcolor": CARD_BG,
        "plot_bgcolor": CARD_BG,
        "font": {"family": "Noto Sans TC, -apple-system, PingFang TC, Microsoft JhengHei, sans-serif", "color": INK},
        "margin": {"l": 44, "r": 20, "t": 48, "b": 42},
        "height": 300,
    }


def _kpi_card(label: str, value: int, accent: str, sub: str = "") -> html.Div:
    return html.Div(
        style={
            "background": CARD_BG,
            "border": f"1.5px solid {LINE}",
            "borderRadius": "18px",
            "padding": "16px 18px",
            "boxShadow": "0 3px 10px -2px rgba(124, 62, 27, 0.06)",
            "minWidth": "0",
        },
        children=[
            html.Div(label, style={"fontSize": "12px", "fontWeight": 700, "color": MUTED}),
            html.Div(
                f"{value:,}",
                style={"fontSize": "28px", "fontWeight": 900, "color": accent, "marginTop": "4px", "lineHeight": 1.1},
            ),
            html.Div(sub, style={"fontSize": "11px", "color": MUTED, "marginTop": "4px"}) if sub else None,
        ],
    )


def create_dash_app() -> Dash:
    """建立並設定 Python Dash 應用程式。"""
    app = Dash(
        __name__,
        requests_pathname_prefix="/ops/dash/",
        routes_pathname_prefix="/",
        title="揪呷 JOEAT · 營運數據分析",
        suppress_callback_exceptions=True,
    )

    app.layout = html.Div(
        style={
            "backgroundColor": BG,
            "minHeight": "100vh",
            "padding": "20px 22px 32px",
            "fontFamily": "Noto Sans TC, -apple-system, PingFang TC, Microsoft JhengHei, sans-serif",
            "color": INK,
        },
        children=[
            # 頂部控制列
            html.Div(
                style={
                    "display": "flex",
                    "flexWrap": "wrap",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "gap": "12px",
                    "background": CARD_BG,
                    "border": f"1.5px solid {LINE}",
                    "borderRadius": "18px",
                    "padding": "14px 18px",
                    "marginBottom": "16px",
                },
                children=[
                    html.Div([
                        html.Div(
                            "Python Dash · 互動式營運數據分析",
                            style={"fontSize": "17px", "fontWeight": 900, "color": INK},
                        ),
                        html.Div(
                            id="dash-updated-at",
                            style={"fontSize": "12px", "color": MUTED, "marginTop": "2px"},
                        ),
                    ]),
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "14px", "flexWrap": "wrap"},
                        children=[
                            dcc.Checklist(
                                id="dash-include-demo",
                                options=[{"label": " 包含示範資料", "value": "demo"}],
                                value=["demo"],
                                style={"fontSize": "13px", "fontWeight": 700, "color": INK},
                                inputStyle={"marginRight": "6px", "accentColor": BRAND},
                            ),
                            html.Button(
                                "重新整理數據",
                                id="dash-refresh-btn",
                                n_clicks=0,
                                style={
                                    "background": BRAND,
                                    "color": "#ffffff",
                                    "border": "none",
                                    "borderRadius": "12px",
                                    "padding": "8px 16px",
                                    "fontSize": "13px",
                                    "fontWeight": 800,
                                    "cursor": "pointer",
                                },
                            ),
                        ],
                    ),
                ],
            ),
            # KPI 指標列
            html.Div(
                id="dash-kpi-grid",
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(165px, 1fr))",
                    "gap": "12px",
                    "marginBottom": "16px",
                },
            ),
            # 互動式圖表 2x2 格線
            html.Div(
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(360px, 1fr))",
                    "gap": "14px",
                },
                children=[
                    html.Div(
                        style={"background": CARD_BG, "border": f"1.5px solid {LINE}", "borderRadius": "18px", "padding": "8px"},
                        children=[dcc.Graph(id="chart-declarations", config={"displayModeBar": False})],
                    ),
                    html.Div(
                        style={"background": CARD_BG, "border": f"1.5px solid {LINE}", "borderRadius": "18px", "padding": "8px"},
                        children=[dcc.Graph(id="chart-pool", config={"displayModeBar": False})],
                    ),
                    html.Div(
                        style={"background": CARD_BG, "border": f"1.5px solid {LINE}", "borderRadius": "18px", "padding": "8px"},
                        children=[dcc.Graph(id="chart-issues", config={"displayModeBar": False})],
                    ),
                    html.Div(
                        style={"background": CARD_BG, "border": f"1.5px solid {LINE}", "borderRadius": "18px", "padding": "8px"},
                        children=[dcc.Graph(id="chart-trend", config={"displayModeBar": False})],
                    ),
                ],
            ),
        ],
    )

    @app.callback(
        Output("dash-kpi-grid", "children"),
        Output("chart-declarations", "figure"),
        Output("chart-pool", "figure"),
        Output("chart-issues", "figure"),
        Output("chart-trend", "figure"),
        Output("dash-updated-at", "children"),
        Input("dash-include-demo", "value"),
        Input("dash-refresh-btn", "n_clicks"),
    )
    def update_dashboard(include_demo_vals: list[str] | None, _n_clicks: int):
        include_demo = bool(include_demo_vals and "demo" in include_demo_vals)
        data = _fetch_analytics(include_demo)
        kpi = data["kpi"]

        coverage_pct = (
            round(kpi["verified_restaurants"] / kpi["restaurants"] * 100, 1)
            if kpi["restaurants"] > 0
            else 0.0
        )

        kpi_cards = [
            _kpi_card("餐廳總數", kpi["restaurants"], INK, "鹽埕區候選資料庫"),
            _kpi_card("第一手已核准餐廳", kpi["verified_restaurants"], OK, f"覆蓋率 {coverage_pct}%"),
            _kpi_card("聚餐場次總數", kpi["sessions"], BRAND, "累計開團數"),
            _kpi_card("累計參與人次", kpi["participants"], BLUE, "完成加入成員"),
            _kpi_card("未結案事故", kpi["open_incidents"], CRIT if kpi["open_incidents"] > 0 else OK, "待處理緊急煞車"),
        ]

        # 圖表 1：聲明審核狀態分布
        if data["decl"]:
            labels = [DECL_STATUS_ZH.get(s, s) for s, _ in data["decl"]]
            values = [c for _, c in data["decl"]]
            colors = [
                WARN if s == "submitted" else OK if s == "approved" else CRIT if s in ("rejected", "withdrawn") else BRAND_LIGHT
                for s, _ in data["decl"]
            ]
            fig_decl = go.Figure(go.Bar(x=labels, y=values, marker_color=colors, text=values, textposition="auto"))
            fig_decl.update_layout(**_base_layout("店家聲明審核狀態分布"), yaxis={"dtick": 1, "gridcolor": LINE})
        else:
            fig_decl = _empty_figure("店家聲明審核狀態分布", "目前尚無店家聲明資料")

        # 圖表 2：餐廳候選池分布
        if data["pool"]:
            p_labels = [POOL_STATUS_ZH.get(s, s) for s, _ in data["pool"]]
            p_values = [c for _, c in data["pool"]]
            fig_pool = go.Figure(
                go.Pie(
                    labels=p_labels,
                    values=p_values,
                    hole=0.48,
                    marker={"colors": [BRAND, BRAND_LIGHT, OK, MUTED]},
                    textinfo="label+percent",
                )
            )
            fig_pool.update_layout(**_base_layout("餐廳候選池狀態分布"), showlegend=False)
        else:
            fig_pool = _empty_figure("餐廳候選池狀態分布")

        # 圖表 3：使用者回報與事故類型分析
        all_kinds = ["allergic_reaction", "wrong_info", "closed", "other"]
        rep_vals = [data["reports"].get(k, 0) for k in all_kinds]
        inc_vals = [data["incidents"].get(k, 0) for k in all_kinds]
        if sum(rep_vals) + sum(inc_vals) > 0:
            k_labels = [ISSUE_KIND_ZH[k] for k in all_kinds]
            fig_issues = go.Figure([
                go.Bar(name="使用者回報", x=k_labels, y=rep_vals, marker_color=WARN),
                go.Bar(name="已立案事故", x=k_labels, y=inc_vals, marker_color=CRIT),
            ])
            fig_issues.update_layout(
                **_base_layout("使用者回報與事故類型分析"),
                barmode="group",
                yaxis={"dtick": 1, "gridcolor": LINE},
                legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 1, "xanchor": "right"},
            )
        else:
            fig_issues = _empty_figure("使用者回報與事故類型分析", "目前尚無回報或事故紀錄")

        # 圖表 4：近期聚餐開團與參與趨勢
        if data["trend"]:
            days = [r["day"] for r in data["trend"]]
            s_cnt = [int(r["session_cnt"]) for r in data["trend"]]
            p_cnt = [int(r["participant_cnt"]) for r in data["trend"]]
            fig_trend = go.Figure([
                go.Bar(name="開團場次", x=days, y=s_cnt, marker_color=BRAND_LIGHT),
                go.Scatter(name="參與人次", x=days, y=p_cnt, mode="lines+markers", line={"color": BRAND, "width": 3}),
            ])
            fig_trend.update_layout(
                **_base_layout("近期聚餐開團與參與趨勢（近 14 日）"),
                yaxis={"dtick": 1, "gridcolor": LINE},
                legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 1, "xanchor": "right"},
            )
        else:
            fig_trend = _empty_figure("近期聚餐開團與參與趨勢（近 14 日）", "目前尚無聚餐場次紀錄")

        updated_text = f"最後更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（{'含示範資料' if include_demo else '僅正式資料'}）"
        return kpi_cards, fig_decl, fig_pool, fig_issues, fig_trend, updated_text

    return app


dash_app = create_dash_app()
