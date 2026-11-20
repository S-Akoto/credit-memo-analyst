import json
import os
from google import genai
from google.genai import types
from src.models import BorrowerPacket, CreditMemoOutput


def _fallback_memo(packet: BorrowerPacket, policy: dict, analysis: dict) -> CreditMemoOutput:
    breaches = [c for c in analysis["covenants"] if c["status"] == "BREACH"]
    watches = [c for c in analysis["covenants"] if c["status"] == "WATCH"]

    if breaches:
        decision = "DECLINE"
        rating = "4 - Substandard"
    elif watches:
        decision = "CONDITIONAL_APPROVAL"
        rating = "3 - Moderate / Watch"
    else:
        decision = "APPROVE"
        rating = "2 - Satisfactory"

    latest = analysis["yearly_metrics"][-1]
    return CreditMemoOutput(
        decision=decision,
        risk_rating=rating,
        executive_summary=(
            f"Recommend {decision.replace('_', ' ')} for {packet.borrower_name}'s requested "
            f"${packet.facility_request.requested_amount:,.0f} {packet.facility_request.facility_type} "
            f"under the {policy['policy_name']}. Pro-forma DSCR stands at {analysis['pro_forma_dscr']:.2f}x "
            f"with pro-forma Debt/EBITDA of {analysis['pro_forma_debt_to_ebitda']:.2f}x."
        ),
        financial_performance_analysis=(
            f"In FY{latest['fiscal_year']}, revenue reached ${latest['revenue']:,.0f} with an EBITDA margin "
            f"of {latest['ebitda_margin_pct']:.1f}% and Current Ratio of {latest['current_ratio']:.2f}x."
        ),
        debt_service_and_stress_commentary=(
            f"Incremental annual debt service of ${analysis['new_annual_debt_service']:,.2f} brings total "
            f"pro-forma debt service to ${analysis['pro_forma_total_debt_service']:,.2f}. Under a "
            f"+{analysis['rate_shock_bps']} bps rate shock, DSCR remains at {analysis['rate_shocked_dscr']:.2f}x."
        ),
        risks_and_mitigants=[
            {
                "risk": packet.qualitative_notes.risks[0] if packet.qualitative_notes.risks else "Working capital volatility",
                "mitigant": f"Secured by {packet.facility_request.collateral} and quarterly financial reporting covenants.",
            }
        ],
        conditions_precedent=[
            f"Perfection of security interest: {packet.facility_request.collateral}.",
            f"Minimum ongoing DSCR covenant of {policy['covenants']['min_dscr']:.2f}x tested semi-annually.",
            "Submission of quarterly internally prepared financial statements and aged A/R-A/P schedules.",
        ],
    )


def generate_credit_memo(packet: BorrowerPacket, policy: dict, analysis: dict) -> CreditMemoOutput:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return _fallback_memo(packet, policy, analysis)

    client = genai.Client(api_key=api_key, http_options={"timeout": 45})

    prompt = f"""
You are a Senior Commercial Credit Underwriter preparing a formal Credit Committee Memorandum.
CRITICAL RULE: Do NOT recalculate or alter any numbers. Cite the exact deterministic ratios, dollar figures, and covenant statuses provided below.

POLICY PROFILE: {policy['policy_name']}
BORROWER: {packet.borrower_name} ({packet.location} | {packet.industry} | {packet.years_in_business} yrs in business)
FACILITY REQUEST: ${packet.facility_request.requested_amount:,.2f} | {packet.facility_request.facility_type} | {packet.facility_request.interest_rate_pct}% | {packet.facility_request.term_months} months
PURPOSE: {packet.facility_request.purpose}
COLLATERAL: {packet.facility_request.collateral}

DETERMINISTIC UNDERWRITING RESULTS:
{json.dumps(analysis, indent=2)}

QUALITATIVE CONTEXT:
{packet.qualitative_notes.model_dump_json(indent=2)}

Draft an institutional-grade Credit Committee Memorandum following the required JSON schema.
"""

    for model_name in ("gemini-2.5-flash", "gemini-2.0-flash"):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CreditMemoOutput,
                    temperature=0.2,
                ),
            )
            return CreditMemoOutput.model_validate_json(response.text)
        except Exception as exc:
            print(f"[warn] Model {model_name} failed ({exc}); trying fallback...")

    return _fallback_memo(packet, policy, analysis)
