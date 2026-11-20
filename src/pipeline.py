import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

import plotly.graph_objects as go
from src.memo import generate_credit_memo
from src.models import BorrowerPacket, CreditMemoOutput
from src.underwrite import analyze_borrower, load_policy


def render_markdown_memo(packet: BorrowerPacket, policy: dict, analysis: dict, memo: CreditMemoOutput) -> str:
    cov_lines = "\n".join(
        f"| {c['metric_name']} | {c['actual_value']:.2f} | {c['threshold_label']} | **{c['status']}** |"
        for c in analysis["covenants"]
    )
    spread_lines = "\n".join(
        f"| FY{m['fiscal_year']} | ${m['revenue']:,.0f} | ${m['ebitda']:,.0f} ({m['ebitda_margin_pct']:.1f}%) | "
        f"{m['current_ratio']:.2f}x | {m['debt_to_ebitda']:.2f}x | {m['historical_dscr']:.2f}x |"
        for m in analysis["yearly_metrics"]
    )
    risk_lines = "\n".join(
        f"- **Risk:** {rm.risk}\n  - **Mitigant:** {rm.mitigant}"
        for rm in memo.risks_and_mitigants
    )
    cp_lines = "\n".join(f"1. {cp}" for cp in memo.conditions_precedent)

    return f"""# CREDIT COMMITTEE MEMORANDUM
**Borrower:** {packet.borrower_name} (`{packet.borrower_id}`)  
**Location / Industry:** {packet.location} | {packet.industry}  
**Policy Profile:** {policy['policy_name']}  
**Recommendation:** **{memo.decision.replace('_', ' ')}** | **Risk Rating:** {memo.risk_rating}  

---

## 1. Proposed Facility Terms
- **Facility:** {packet.facility_request.facility_type} — **${packet.facility_request.requested_amount:,.2f}**
- **Pricing & Tenor:** {packet.facility_request.interest_rate_pct:.2f}% fixed | {packet.facility_request.term_months} months
- **Pro-Forma Annual Debt Service:** ${analysis['pro_forma_total_debt_service']:,.2f} (Incremental: ${analysis['new_annual_debt_service']:,.2f})
- **Purpose:** {packet.facility_request.purpose}
- **Collateral:** {packet.facility_request.collateral}

## 2. Executive Recommendation
{memo.executive_summary}

## 3. Policy Covenant Scorecard (FY{analysis['latest_year']} Pro-Forma)
| Covenant Metric | Actual | Policy Threshold | Status |
| :--- | :---: | :---: | :---: |
{cov_lines}

## 4. Historical Financial Spread Summary
| Fiscal Year | Revenue | EBITDA (Margin) | Current Ratio | Debt / EBITDA | Historical DSCR |
| :--- | :---: | :---: | :---: | :---: | :---: |
{spread_lines}

### Financial Performance Commentary
{memo.financial_performance_analysis}

## 5. Debt Service & Sensitivity Stress Analysis
- **Base Pro-Forma DSCR:** {analysis['pro_forma_dscr']:.2f}x
- **Rate-Shocked DSCR (+{analysis['rate_shock_bps']} bps):** {analysis['rate_shocked_dscr']:.2f}x

{memo.debt_service_and_stress_commentary}

## 6. Key Credit Risks & Structural Mitigants
{risk_lines}

## 7. Conditions Precedent & Ongoing Covenants
{cp_lines}
"""


def build_charts_html(packet: BorrowerPacket, analysis: dict) -> tuple[str, str]:
    years = [f"FY{m['fiscal_year']}" for m in analysis["yearly_metrics"]]
    revs = [m["revenue"] for m in analysis["yearly_metrics"]]
    ebitdas = [m["ebitda"] for m in analysis["yearly_metrics"]]

    fig_trend = go.Figure()
    fig_trend.add_bar(x=years, y=revs, name="Revenue ($)", marker_color="#2563eb")
    fig_trend.add_bar(x=years, y=ebitdas, name="EBITDA ($)", marker_color="#0d9488")
    fig_trend.update_layout(
        title=dict(text="3-Year Revenue & EBITDA Trajectory", font=dict(size=15)),
        barmode="group",
        template="plotly_white",
        height=320,
        margin=dict(l=15, r=15, t=45, b=20),
    )

    st = analysis["stress_test"]
    x_labels = [f"COGS {c:+.1f}%" for c in st["cogs_shocks_pct"]]
    y_labels = [f"Rev {r:+.0f}%" for r in st["revenue_shocks_pct"]]
    z_vals = st["dscr_matrix"]

    fig_heat = go.Figure(
        data=go.Heatmap(
            z=z_vals,
            x=x_labels,
            y=y_labels,
            text=[[f"{val:.2f}x" for val in row] for row in z_vals],
            texttemplate="%{text}",
            colorscale=[[0.0, "#dc2626"], [0.45, "#f59e0b"], [1.0, "#16a34a"]],
            zmin=0.80,
            zmax=1.60,
            colorbar=dict(title="DSCR"),
        )
    )
    fig_heat.update_layout(
        title=dict(text="Pro-Forma DSCR Stress Matrix (Rev vs. COGS)", font=dict(size=15)),
        template="plotly_white",
        height=320,
        margin=dict(l=15, r=15, t=45, b=20),
    )

    return (
        fig_trend.to_html(full_html=False, include_plotlyjs=False),
        fig_heat.to_html(full_html=False, include_plotlyjs=False),
    )


def build_html_dossier(cases: list[dict]):
    tabs_html = []
    panels_html = []

    for idx, case in enumerate(cases):
        pkt: BorrowerPacket = case["packet"]
        pol: dict = case["policy"]
        ana: dict = case["analysis"]
        memo: CreditMemoOutput = case["memo"]
        trend_html, heat_html = build_charts_html(pkt, ana)

        active_cls = "active" if idx == 0 else ""
        hidden_cls = "" if idx == 0 else "hidden"
        tabs_html.append(
            f'<button class="tab-btn {active_cls}" onclick="selectCase(\'{pkt.borrower_id}\', this)">'
            f'{html.escape(pkt.borrower_name)}</button>'
        )

        badge_bg = "#16a34a" if memo.decision == "APPROVE" else ("#d97706" if memo.decision == "CONDITIONAL_APPROVAL" else "#dc2626")
        cov_rows = []
        for c in ana["covenants"]:
            st_color = "#16a34a" if c["status"] == "PASS" else ("#d97706" if c["status"] == "WATCH" else "#dc2626")
            cov_rows.append(
                f"<tr><td>{html.escape(c['metric_name'])}</td>"
                f"<td><strong>{c['actual_value']:.2f}</strong></td>"
                f"<td>{html.escape(c['threshold_label'])}</td>"
                f"<td><span class='pill' style='background:{st_color};'>{c['status']}</span></td></tr>"
            )

        rm_html = "".join(
            f"<li><strong>Risk:</strong> {html.escape(rm.risk)}<br><strong>Mitigant:</strong> {html.escape(rm.mitigant)}</li>"
            for rm in memo.risks_and_mitigants
        )
        cp_html = "".join(f"<li>{html.escape(cp)}</li>" for cp in memo.conditions_precedent)

        panels_html.append(f"""
        <div class="case-panel {hidden_cls}" id="panel-{pkt.borrower_id}">
          <div class="kpi-grid">
            <div class="kpi-card">
              <div class="kpi-label">Committee Decision</div>
              <div class="kpi-value"><span class="pill" style="background:{badge_bg};font-size:0.95rem;">{memo.decision.replace('_', ' ')}</span></div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">Facility Request</div>
              <div class="kpi-value">${pkt.facility_request.requested_amount:,.0f}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">Pro-Forma DSCR</div>
              <div class="kpi-value">{ana['pro_forma_dscr']:.2f}x</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">Pro-Forma Debt / EBITDA</div>
              <div class="kpi-value">{ana['pro_forma_debt_to_ebitda']:.2f}x</div>
            </div>
          </div>

          <div class="chart-grid">
            <div class="card">{trend_html}</div>
            <div class="card">{heat_html}</div>
          </div>

          <div class="memo-grid">
            <div class="card">
              <h3 style="margin-top:0;">Policy Covenant Scorecard ({html.escape(pol['policy_name'])})</h3>
              <table class="cov-table">
                <thead><tr><th>Metric</th><th>Actual</th><th>Threshold</th><th>Status</th></tr></thead>
                <tbody>{''.join(cov_rows)}</tbody>
              </table>
              <p style="font-size:0.85rem;color:#475569;margin-top:0.9rem;">
                <strong>Rate Shock (+{ana['rate_shock_bps']} bps):</strong> DSCR moves to <strong>{ana['rate_shocked_dscr']:.2f}x</strong><br>
                <strong>Collateral:</strong> {html.escape(pkt.facility_request.collateral)}
              </p>
            </div>

            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <h3 style="margin-top:0;">Credit Committee Memorandum</h3>
                <span style="font-size:0.82rem;font-weight:600;color:#475569;">Risk Rating: {html.escape(memo.risk_rating)}</span>
              </div>
              <p><strong>Executive Summary:</strong> {html.escape(memo.executive_summary)}</p>
              <p><strong>Financial Performance:</strong> {html.escape(memo.financial_performance_analysis)}</p>
              <p><strong>Debt Service & Stress:</strong> {html.escape(memo.debt_service_and_stress_commentary)}</p>
              <h4>Risks & Structural Mitigants</h4>
              <ul>{rm_html}</ul>
              <h4>Conditions Precedent & Covenants</h4>
              <ol>{cp_html}</ol>
            </div>
          </div>
        </div>
        """)

    updated_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Deterministic Credit Underwriting & Memo Engine</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 2rem; background: #f8fafc; color: #0f172a; }}
    .container {{ max-width: 1240px; margin: auto; }}
    header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 1rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 1rem; margin-bottom: 1.5rem; }}
    .tab-bar {{ display: inline-flex; background: #e2e8f0; padding: 0.25rem; border-radius: 8px; gap: 0.25rem; }}
    .tab-btn {{ border: none; background: transparent; padding: 0.55rem 1rem; border-radius: 6px; font-size: 0.9rem; font-weight: 600; color: #475569; cursor: pointer; }}
    .tab-btn.active {{ background: #fff; color: #1d4ed8; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
    .kpi-card {{ background: #fff; border-radius: 8px; padding: 1.15rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); border-left: 4px solid #2563eb; }}
    .kpi-label {{ font-size: 0.78rem; text-transform: uppercase; color: #64748b; font-weight: 600; }}
    .kpi-value {{ font-size: 1.5rem; font-weight: 700; margin-top: 0.35rem; }}
    .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; margin-bottom: 1.5rem; }}
    .memo-grid {{ display: grid; grid-template-columns: 1fr 1.45fr; gap: 1.25rem; }}
    @media (max-width: 900px) {{ .chart-grid, .memo-grid {{ grid-template-columns: 1fr; }} }}
    .card {{ background: #fff; border-radius: 8px; padding: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    .cov-table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
    .cov-table th, .cov-table td {{ padding: 0.65rem; text-align: left; border-bottom: 1px solid #e2e8f0; }}
    .cov-table th {{ background: #f1f5f9; }}
    .pill {{ display: inline-block; padding: 0.22rem 0.55rem; border-radius: 999px; color: #fff; font-size: 0.78rem; font-weight: 700; }}
    .hidden {{ display: none !important; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1 style="margin:0 0 0.35rem 0;">Commercial Credit Underwriting & Memo Workbench</h1>
        <p style="margin:0;color:#475569;">Deterministic Ratio & Stress Engine + Structured Gemini Credit Committee Synthesis | Updated: <strong>{updated_ts}</strong></p>
      </div>
      <div class="tab-bar">{''.join(tabs_html)}</div>
    </header>
    {''.join(panels_html)}
  </div>
  <script>
    function selectCase(id, btn) {{
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.case-panel').forEach(p => p.classList.add('hidden'));
      document.getElementById('panel-' + id).classList.remove('hidden');
      window.dispatchEvent(new Event('resize'));
    }}
  </script>
</body>
</html>
"""
    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run deterministic credit underwriting & memo synthesis.")
    parser.add_argument("--borrower", type=str, default=None, help="Optional path to a single borrower JSON file.")
    args = parser.parse_args()

    files = [Path(args.borrower)] if args.borrower else sorted(Path("data/sample_borrowers").glob("*.json"))
    Path("output").mkdir(exist_ok=True)
    cases = []

    for fp in files:
        raw = json.loads(fp.read_text(encoding="utf-8"))
        packet = BorrowerPacket.model_validate(raw)
        policy = load_policy(Path("config") / f"{packet.policy_id}.yaml")
        analysis = analyze_borrower(packet, policy)
        memo = generate_credit_memo(packet, policy, analysis)

        md_text = render_markdown_memo(packet, policy, analysis, memo)
        out_md = Path("output") / f"{packet.borrower_id}_{fp.stem}_memo.md"
        out_md.write_text(md_text, encoding="utf-8")
        print(f"[ok] Underwrote {packet.borrower_name} -> {out_md} (Decision: {memo.decision})")
        cases.append({"packet": packet, "policy": policy, "analysis": analysis, "memo": memo})

    build_html_dossier(cases)
    print("[ok] Built multi-borrower interactive dossier -> docs/index.html")


if __name__ == "__main__":
    main()
