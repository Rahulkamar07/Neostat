"""Pydantic extraction schemas per document type.

Documents in scope (case study Section 2 & 4.2):
- invoice
- balance_sheet
- profit_and_loss
- cash_flow_statement

All schemas adhere strictly to:
1. Field grounding: value, confidence (optional float), evidence (source text snippet, page number).
2. Complete table / line item extraction.
3. Comparative period support for financial statements.
4. Explicit None for missing values (never hallucinated or guessed).
"""

from __future__ import annotations

from typing import Any, Generic, Literal, Optional, TypeVar, Union
from pydantic import BaseModel, Field

DocumentType = Literal["invoice", "balance_sheet", "profit_and_loss", "cash_flow_statement"]

T = TypeVar("T")


class Evidence(BaseModel):
    """Grounding evidence linking an extracted value to the source document."""

    source_text: Optional[str] = Field(None, description="Exact or verbatim source text snippet")
    page_number: Optional[int] = Field(None, description="1-indexed page where value was found")


class ExtractedField(BaseModel, Generic[T]):
    """Standard grounded field wrapper with optional confidence and evidence.

    Accepts both nested evidence: `{"evidence": {"source_text": "...", "page_number": 1}}`
    and flat evidence: `{"source_text": "...", "page_number": 1}`.
    """

    value: Optional[T] = Field(None, description="Extracted value, or null if not present in document")
    confidence: Optional[float] = Field(None, description="Optional confidence score between 0.0 and 1.0")
    evidence: Optional[Evidence] = Field(None, description="Supporting source evidence")
    page_number: Optional[int] = Field(None, description="Flat page number representation")
    source_text: Optional[str] = Field(None, description="Flat source text representation")

    def model_post_init(self, __context: Any) -> None:
        # Normalize between flat fields and nested evidence object
        if self.evidence is None and (self.source_text is not None or self.page_number is not None):
            self.evidence = Evidence(source_text=self.source_text, page_number=self.page_number)
        elif self.evidence is not None:
            if self.page_number is None and self.evidence.page_number is not None:
                self.page_number = self.evidence.page_number
            if self.source_text is None and self.evidence.source_text is not None:
                self.source_text = self.evidence.source_text


# Convenience aliases
StringField = ExtractedField[str]
FloatField = ExtractedField[float]
IntegerField = ExtractedField[int]


# ==============================================================================
# 1. INVOICE SCHEMA
# ==============================================================================

class InvoiceLineItem(BaseModel):
    """Single line item from an invoice."""

    description: Optional[str] = Field(None, description="Description of the product/service")
    quantity: Optional[float] = Field(None, description="Quantity purchased")
    unit_price: Optional[float] = Field(None, description="Unit price per item")
    amount: Optional[float] = Field(None, description="Total line amount (quantity * unit_price)")
    tax_rate: Optional[float] = Field(None, description="Tax / GST percentage if specified")
    discount: Optional[float] = Field(None, description="Discount amount on line item if specified")
    page_number: Optional[int] = Field(None, description="Page number where line item appears")


class InvoiceData(BaseModel):
    """Structured extraction output for Invoices."""

    invoice_number: StringField = Field(default_factory=StringField)
    invoice_date: StringField = Field(default_factory=StringField)
    due_date: StringField = Field(default_factory=StringField)
    vendor_name: StringField = Field(default_factory=StringField)
    vendor_address: StringField = Field(default_factory=StringField)
    customer_name: StringField = Field(default_factory=StringField)
    customer_address: StringField = Field(default_factory=StringField)
    currency: StringField = Field(default_factory=StringField)

    subtotal: FloatField = Field(default_factory=FloatField)
    tax_amount: FloatField = Field(default_factory=FloatField)
    tax_rate: FloatField = Field(default_factory=FloatField)
    discount: FloatField = Field(default_factory=FloatField)
    rounding_adjustment: FloatField = Field(default_factory=FloatField)
    total_amount: FloatField = Field(default_factory=FloatField)
    cash_paid: FloatField = Field(default_factory=FloatField)
    change_given: FloatField = Field(default_factory=FloatField)

    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    additional_fields: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# 2. BALANCE SHEET SCHEMA
# ==============================================================================

class StatementHeader(BaseModel):
    """Common header information for financial statements."""

    company_name: StringField = Field(default_factory=StringField)
    statement_title: StringField = Field(default_factory=StringField)
    currency: StringField = Field(default_factory=StringField)
    unit_multiplier: StringField = Field(
        default_factory=StringField,
        description="e.g. 'in thousands', 'in Millions', 'in Crores', etc.",
    )
    reporting_period: StringField = Field(
        default_factory=StringField,
        description="Current reporting period/date, e.g. 'March 31, 2017'",
    )
    comparative_period: StringField = Field(
        default_factory=StringField,
        description="Prior comparison period/date, e.g. 'March 31, 2016'",
    )


class FinancialLineItem(BaseModel):
    """Generic financial statement row with current and comparative values."""

    line_item_name: str = Field(..., description="Name / description of the financial line item")
    schedule_number: Optional[str] = Field(None, description="Schedule or note number reference")
    current_value: Optional[float] = Field(None, description="Value for the current period")
    comparative_value: Optional[float] = Field(None, description="Value for the comparative period")
    evidence: Optional[Evidence] = Field(None, description="Source evidence")


class BalanceSheetPeriodData(BaseModel):
    """Core balance sheet totals for a specific period."""

    period: Optional[str] = Field(None, description="e.g. '31-Mar-17' or '31-Mar-16'")
    # Liabilities & Capital
    capital: Optional[float] = Field(None, description="Capital / Share capital")
    reserves_and_surplus: Optional[float] = Field(None, description="Reserves and surplus")
    minority_interest: Optional[float] = Field(None, description="Minority interest")
    deposits: Optional[float] = Field(None, description="Deposits (for banks / financials)")
    borrowings: Optional[float] = Field(None, description="Borrowings / Debt")
    other_liabilities_provisions: Optional[float] = Field(None, description="Other liabilities and provisions")
    total_capital_and_liabilities: Optional[float] = Field(
        None, description="Reported total capital & liabilities (or total liabilities + equity)"
    )

    # Assets
    cash_and_balances_with_central_bank: Optional[float] = Field(None)
    balances_with_banks_money_at_call: Optional[float] = Field(None)
    investments: Optional[float] = Field(None)
    advances_or_loans: Optional[float] = Field(None)
    fixed_assets: Optional[float] = Field(None)
    other_assets: Optional[float] = Field(None)
    total_assets: Optional[float] = Field(None, description="Reported total assets")


class BalanceSheetData(BaseModel):
    """Structured extraction output for Balance Sheets."""

    header: StatementHeader = Field(default_factory=StatementHeader)
    current_period: BalanceSheetPeriodData = Field(default_factory=BalanceSheetPeriodData)
    comparative_period: BalanceSheetPeriodData = Field(default_factory=BalanceSheetPeriodData)
    line_items: list[FinancialLineItem] = Field(default_factory=list)
    additional_fields: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# 3. PROFIT & LOSS SCHEMA
# ==============================================================================

class ProfitLossPeriodData(BaseModel):
    """Core P&L values for a single period."""

    period: Optional[str] = Field(None, description="Period date/year")
    # Income
    interest_earned: Optional[float] = Field(None, description="Interest earned (financials) or revenue")
    other_income: Optional[float] = Field(None, description="Other non-interest income")
    total_income: Optional[float] = Field(None, description="Reported total income / revenue")

    # Expenditure
    interest_expended: Optional[float] = Field(None, description="Interest expended / COGS")
    operating_expenses: Optional[float] = Field(None, description="Operating expenses")
    provisions_and_contingencies: Optional[float] = Field(None, description="Provisions and contingencies")
    total_expenditure: Optional[float] = Field(None, description="Reported total expenditure / expenses")

    # Profit / Loss
    operating_profit: Optional[float] = Field(None, description="Operating profit before provisions")
    net_profit_before_minority: Optional[float] = Field(None, description="Net profit for the year")
    minority_interest: Optional[float] = Field(None, description="Minority interest deduction")
    share_in_profit_of_associates: Optional[float] = Field(None, description="Add: share in associates")
    consolidated_net_profit: Optional[float] = Field(
        None, description="Consolidated net profit attributable to Group"
    )

    # Appropriations
    profit_brought_forward: Optional[float] = Field(None, description="Balance in P&L brought forward")
    total_available_for_appropriation: Optional[float] = Field(
        None, description="Total profit available for appropriation"
    )
    transfer_to_statutory_reserve: Optional[float] = Field(None)
    proposed_dividend: Optional[float] = Field(None)
    transfer_to_general_reserve: Optional[float] = Field(None)


class ProfitLossData(BaseModel):
    """Structured extraction output for Profit & Loss statements."""

    header: StatementHeader = Field(default_factory=StatementHeader)
    current_period: ProfitLossPeriodData = Field(default_factory=ProfitLossPeriodData)
    comparative_period: ProfitLossPeriodData = Field(default_factory=ProfitLossPeriodData)
    line_items: list[FinancialLineItem] = Field(default_factory=list)
    additional_fields: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# 4. CASH FLOW STATEMENT SCHEMA
# ==============================================================================

class CashFlowPeriodData(BaseModel):
    """Core Cash Flow totals for a single period."""

    period: Optional[str] = Field(None, description="Period date/year")
    profit_before_tax: Optional[float] = Field(None, description="Profit before income tax")
    net_cash_operating: Optional[float] = Field(
        None, description="Net cash flow from/used in operating activities"
    )
    net_cash_investing: Optional[float] = Field(
        None, description="Net cash flow from/used in investing activities"
    )
    net_cash_financing: Optional[float] = Field(
        None, description="Net cash flow from/used in financing activities"
    )
    fx_translation_adjustment: Optional[float] = Field(
        0.0, description="Foreign exchange translation adjustments"
    )
    net_increase_in_cash: Optional[float] = Field(
        None, description="Net increase / decrease in cash and cash equivalents"
    )

    opening_cash_equivalents: Optional[float] = Field(
        None, description="Cash & cash equivalents at beginning of period"
    )
    cash_acquired_adjustments: Optional[float] = Field(
        0.0, description="Cash acquired on amalgamation / adjustments"
    )
    closing_cash_equivalents: Optional[float] = Field(
        None, description="Cash & cash equivalents at end of period"
    )


class CashFlowData(BaseModel):
    """Structured extraction output for Cash Flow statements."""

    header: StatementHeader = Field(default_factory=StatementHeader)
    current_period: CashFlowPeriodData = Field(default_factory=CashFlowPeriodData)
    comparative_period: CashFlowPeriodData = Field(default_factory=CashFlowPeriodData)
    line_items: list[FinancialLineItem] = Field(default_factory=list)
    additional_fields: dict[str, Any] = Field(default_factory=dict)


# Unified extracted data container
ExtractedDataModel = Union[InvoiceData, BalanceSheetData, ProfitLossData, CashFlowData]
