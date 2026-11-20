from typing import Literal
from pydantic import BaseModel, Field


class FacilityRequest(BaseModel):
    facility_type: str
    requested_amount: float
    interest_rate_pct: float
    term_months: int
    collateral: str
    purpose: str


class AnnualFinancials(BaseModel):
    fiscal_year: int
    revenue: float
    cogs: float
    operating_expenses: float
    depreciation_amortization: float
    interest_expense: float
    taxes: float
    cash_and_equivalents: float
    accounts_receivable: float
    inventory: float
    total_current_assets: float
    total_assets: float
    accounts_payable: float
    short_term_debt: float
    total_current_liabilities: float
    long_term_debt: float
    total_liabilities: float
    total_equity: float
    existing_annual_principal_payments: float


class QualitativeNotes(BaseModel):
    business_overview: str
    strengths: list[str]
    risks: list[str]
    management_experience: str


class BorrowerPacket(BaseModel):
    borrower_id: str
    borrower_name: str
    policy_id: str
    location: str
    industry: str
    years_in_business: int
    facility_request: FacilityRequest
    financials: list[AnnualFinancials]
    qualitative_notes: QualitativeNotes


class CovenantCheck(BaseModel):
    metric_name: str
    actual_value: float
    threshold_label: str
    status: Literal["PASS", "WATCH", "BREACH"]


class RiskMitigantPair(BaseModel):
    risk: str = Field(description="Specific quantitative or operational credit risk identified")
    mitigant: str = Field(description="Concrete structural, collateral, or covenant mitigant")


class CreditMemoOutput(BaseModel):
    decision: Literal["APPROVE", "CONDITIONAL_APPROVAL", "DECLINE"]
    risk_rating: Literal["1 - Low Risk", "2 - Satisfactory", "3 - Moderate / Watch", "4 - Substandard"]
    executive_summary: str = Field(description="Concise 3-4 sentence Credit Committee recommendation citing exact ratios")
    financial_performance_analysis: str = Field(description="Multi-year revenue, margin, liquidity, and leverage trajectory")
    debt_service_and_stress_commentary: str = Field(description="Pro-forma DSCR and stress-test resilience analysis")
    risks_and_mitigants: list[RiskMitigantPair]
    conditions_precedent: list[str] = Field(description="Actionable closing conditions and ongoing financial covenants")
