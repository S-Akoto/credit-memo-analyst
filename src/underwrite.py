import math
from pathlib import Path
import yaml
from src.models import BorrowerPacket, CovenantCheck


def load_policy(policy_path: str | Path) -> dict:
    with open(policy_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_annual_debt_service(principal: float, annual_rate_pct: float, term_months: int) -> float:
    r = (annual_rate_pct / 100.0) / 12.0
    if r == 0:
        monthly = principal / term_months
    else:
        monthly = principal * (r * math.pow(1 + r, term_months)) / (math.pow(1 + r, term_months) - 1)
    return round(monthly * 12.0, 2)


def analyze_borrower(packet: BorrowerPacket, policy: dict) -> dict:
    years_sorted = sorted(packet.financials, key=lambda x: x.fiscal_year)
    yearly_metrics = []

    for fy in years_sorted:
        gross_profit = fy.revenue - fy.cogs
        ebit = gross_profit - fy.operating_expenses
        ebitda = ebit + fy.depreciation_amortization
        total_debt = fy.short_term_debt + fy.long_term_debt
        existing_ds = fy.interest_expense + fy.existing_annual_principal_payments

        gross_margin_pct = (gross_profit / fy.revenue) * 100.0 if fy.revenue else 0.0
        ebitda_margin_pct = (ebitda / fy.revenue) * 100.0 if fy.revenue else 0.0
        current_ratio = fy.total_current_assets / fy.total_current_liabilities if fy.total_current_liabilities else 0.0
        debt_to_ebitda = total_debt / ebitda if ebitda > 0 else 99.0
        interest_coverage = ebit / fy.interest_expense if fy.interest_expense > 0 else 99.0
        historical_dscr = (ebitda - fy.taxes) / existing_ds if existing_ds > 0 else 99.0
        ar_days = (fy.accounts_receivable / fy.revenue) * 365.0 if fy.revenue else 0.0
        inv_days = (fy.inventory / fy.cogs) * 365.0 if fy.cogs else 0.0

        yearly_metrics.append({
            "fiscal_year": fy.fiscal_year,
            "revenue": round(fy.revenue, 2),
            "gross_profit": round(gross_profit, 2),
            "ebitda": round(ebitda, 2),
            "taxes": round(fy.taxes, 2),
            "total_debt": round(total_debt, 2),
            "existing_debt_service": round(existing_ds, 2),
            "gross_margin_pct": round(gross_margin_pct, 2),
            "ebitda_margin_pct": round(ebitda_margin_pct, 2),
            "current_ratio": round(current_ratio, 2),
            "debt_to_ebitda": round(debt_to_ebitda, 2),
            "interest_coverage": round(interest_coverage, 2),
            "historical_dscr": round(historical_dscr, 2),
            "ar_days": round(ar_days, 1),
            "inv_days": round(inv_days, 1),
        })

    latest_fy = years_sorted[-1]
    latest = yearly_metrics[-1]
    req = packet.facility_request

    new_annual_ds = compute_annual_debt_service(req.requested_amount, req.interest_rate_pct, req.term_months)
    pro_forma_total_debt = latest["total_debt"] + req.requested_amount
    pro_forma_total_ds = latest["existing_debt_service"] + new_annual_ds
    cash_available_for_ds = latest["ebitda"] - latest["taxes"]

    pro_forma_dscr = round(cash_available_for_ds / pro_forma_total_ds, 2)
    pro_forma_debt_to_ebitda = round(pro_forma_total_debt / latest["ebitda"], 2) if latest["ebitda"] > 0 else 99.0

    # Covenant Evaluation against Policy
    cov = policy["covenants"]
    dscr_status = (
        "PASS" if pro_forma_dscr >= cov["min_dscr"]
        else ("WATCH" if pro_forma_dscr >= cov["watch_dscr"] else "BREACH")
    )
    lev_status = (
        "PASS" if pro_forma_debt_to_ebitda <= cov["max_debt_to_ebitda"]
        else ("WATCH" if pro_forma_debt_to_ebitda <= cov["max_debt_to_ebitda"] + 0.5 else "BREACH")
    )
    cr_status = (
        "PASS" if latest["current_ratio"] >= cov["min_current_ratio"]
        else ("WATCH" if latest["current_ratio"] >= cov["min_current_ratio"] - 0.10 else "BREACH")
    )
    ic_status = "PASS" if latest["interest_coverage"] >= cov["min_interest_coverage"] else "BREACH"
    margin_status = "PASS" if latest["ebitda_margin_pct"] >= cov["min_ebitda_margin_pct"] else "WATCH"

    covenants = [
        CovenantCheck(
            metric_name="Pro-Forma DSCR",
            actual_value=pro_forma_dscr,
            threshold_label=f">= {cov['min_dscr']:.2f}x",
            status=dscr_status,
        ),
        CovenantCheck(
            metric_name="Pro-Forma Debt / EBITDA",
            actual_value=pro_forma_debt_to_ebitda,
            threshold_label=f"<= {cov['max_debt_to_ebitda']:.2f}x",
            status=lev_status,
        ),
        CovenantCheck(
            metric_name="Current Ratio",
            actual_value=latest["current_ratio"],
            threshold_label=f">= {cov['min_current_ratio']:.2f}x",
            status=cr_status,
        ),
        CovenantCheck(
            metric_name="Interest Coverage (EBIT/Int)",
            actual_value=latest["interest_coverage"],
            threshold_label=f">= {cov['min_interest_coverage']:.2f}x",
            status=ic_status,
        ),
        CovenantCheck(
            metric_name="EBITDA Margin (%)",
            actual_value=latest["ebitda_margin_pct"],
            threshold_label=f">= {cov['min_ebitda_margin_pct']:.1f}%",
            status=margin_status,
        ),
    ]

    # 2D Stress Test Matrix: Revenue Shock x COGS Cost Inflation
    rev_shocks = policy["stress_test"]["revenue_shocks_pct"]
    cogs_shocks = policy["stress_test"]["cogs_shocks_pct"]
    stress_matrix = []
    breakeven_cases = []

    for r_shock in rev_shocks:
        row_vals = []
        for c_shock in cogs_shocks:
            stressed_rev = latest_fy.revenue * (1.0 + r_shock / 100.0)
            stressed_cogs = latest_fy.cogs * (1.0 + r_shock / 100.0) * (1.0 + c_shock / 100.0)
            stressed_ebitda = (stressed_rev - stressed_cogs - latest_fy.operating_expenses) + latest_fy.depreciation_amortization
            stressed_dscr = round((stressed_ebitda - latest_fy.taxes) / pro_forma_total_ds, 2)
            row_vals.append(stressed_dscr)
            if stressed_dscr < 1.00:
                breakeven_cases.append(f"Rev {r_shock:+.0f}% / COGS {c_shock:+.1f}% -> DSCR {stressed_dscr:.2f}x")
        stress_matrix.append(row_vals)

    # Interest Rate Shock (+bps on new facility)
    shock_bps = policy["stress_test"]["rate_shock_bps"]
    shocked_rate = req.interest_rate_pct + (shock_bps / 100.0)
    shocked_new_ds = compute_annual_debt_service(req.requested_amount, shocked_rate, req.term_months)
    rate_shocked_dscr = round(cash_available_for_ds / (latest["existing_debt_service"] + shocked_new_ds), 2)

    return {
        "latest_year": latest_fy.fiscal_year,
        "yearly_metrics": yearly_metrics,
        "new_annual_debt_service": new_annual_ds,
        "pro_forma_total_debt": round(pro_forma_total_debt, 2),
        "pro_forma_total_debt_service": round(pro_forma_total_ds, 2),
        "pro_forma_dscr": pro_forma_dscr,
        "pro_forma_debt_to_ebitda": pro_forma_debt_to_ebitda,
        "rate_shock_bps": shock_bps,
        "rate_shocked_dscr": rate_shocked_dscr,
        "covenants": [c.model_dump() for c in covenants],
        "stress_test": {
            "revenue_shocks_pct": rev_shocks,
            "cogs_shocks_pct": cogs_shocks,
            "dscr_matrix": stress_matrix,
            "sub_1x_scenarios": breakeven_cases[:5],
        },
    }
