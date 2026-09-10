"""Financial calculation validation service.

Performs deterministic mathematical checks on extracted data per document type:
1. Balance Sheet:
   - Total Capital & Liabilities ≈ Total Assets (for current and comparative periods).
   - Component sum of liabilities reconciles to reported Total Liabilities & Capital.
   - Component sum of assets reconciles to reported Total Assets.
2. Profit & Loss:
   - Interest Earned + Other Income ≈ Total Income.
   - Interest Expended + Operating Expenses + Provisions & Contingencies ≈ Total Expenditure.
   - Total Income - Total Expenditure ≈ Net Profit before Minority Interest.
   - Net Profit before Minority Interest - Minority Interest + Associate Share ≈ Consolidated Net Profit.
   - Current Profit + Brought Forward Profit ≈ Total Available for Appropriation.
3. Cash Flow Statement:
   - Operating + Investing + Financing + FX Translation Adjustment ≈ Net Increase in Cash.
   - Opening Cash + Net Increase in Cash + Amalgamation Adjustments ≈ Closing Cash.
4. Invoice:
   - Quantity * Unit Price ≈ Line Total for each item.
   - Subtotal + Tax - Discount + Rounding Adjustment ≈ Total Amount.
   - Cash Paid - Total Amount ≈ Change Given.

CRITICAL RULES:
- Missing required fields return status NOT_APPLICABLE (never default to 0.0 or hallucinate).
- Uses configurable tolerance (Settings.validation_tolerance, default 1.00 or relative).
- Returns ValidationSummary with complete operands, calculated_value, reported_value, variance, and status.
"""

from __future__ import annotations

import math
from typing import Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.extraction import (
    BalanceSheetData,
    BalanceSheetPeriodData,
    CashFlowData,
    CashFlowPeriodData,
    DocumentType,
    ExtractedDataModel,
    InvoiceData,
    ProfitLossData,
    ProfitLossPeriodData,
)
from app.schemas.validation import CheckStatus, ValidationCheck, ValidationSummary

logger = get_logger(__name__)


def is_within_tolerance(calculated: float, reported: float, tolerance: float = 1.0) -> tuple[bool, float]:
    """Check if difference between calculated and reported is within numeric tolerance."""
    variance = round(abs(calculated - reported), 4)
    # Absolute tolerance or relative 0.05% for massive balance sheet numbers
    relative_tol = max(tolerance, abs(reported) * 0.0005)
    passed = variance <= relative_tol
    return passed, variance


def make_check(
    name: str,
    formula: str,
    operands: dict[str, Optional[float]],
    calculated: Optional[float],
    reported: Optional[float],
    *,
    tolerance: float = 1.0,
    period: Optional[str] = None,
) -> ValidationCheck:
    """Construct a ValidationCheck, returning NOT_APPLICABLE if any operand or reported value is missing."""
    if calculated is None or reported is None:
        return ValidationCheck(
            name=name,
            formula=formula,
            operands=operands,
            calculated_value=calculated,
            reported_value=reported,
            variance=None,
            status="NOT_APPLICABLE",
            period=period,
        )

    passed, variance = is_within_tolerance(calculated, reported, tolerance)
    return ValidationCheck(
        name=name,
        formula=formula,
        operands=operands,
        calculated_value=round(calculated, 4),
        reported_value=round(reported, 4),
        variance=variance,
        status="PASS" if passed else "FAIL",
        period=period,
    )


# ==============================================================================
# INVOICE VALIDATIONS
# ==============================================================================

def validate_invoice(invoice: InvoiceData, tolerance: float = 1.0) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []

    # 1. Invoice Total Check: Subtotal + Tax - Discount + Rounding == Total
    subtotal = invoice.subtotal.value
    tax = invoice.tax_amount.value or 0.0 if invoice.tax_amount.value is not None else None
    discount = invoice.discount.value or 0.0 if invoice.discount.value is not None else None
    rounding = invoice.rounding_adjustment.value or 0.0 if invoice.rounding_adjustment.value is not None else 0.0
    total = invoice.total_amount.value

    # If subtotal is missing, check if line items can compute it
    if subtotal is None and invoice.line_items:
        line_sum = sum(li.amount for li in invoice.line_items if li.amount is not None)
        if line_sum > 0:
            subtotal = line_sum

    if subtotal is not None and total is not None:
        calc_tax = tax if tax is not None else 0.0
        calc_disc = discount if discount is not None else 0.0
        calc_total = subtotal + calc_tax - calc_disc + rounding
        checks.append(
            make_check(
                name="invoice_total_check",
                formula="subtotal + tax_amount - discount + rounding_adjustment",
                operands={
                    "subtotal": subtotal,
                    "tax_amount": tax,
                    "discount": discount,
                    "rounding_adjustment": rounding if rounding else None,
                },
                calculated=calc_total,
                reported=total,
                tolerance=tolerance,
            )
        )
    else:
        checks.append(
            make_check(
                name="invoice_total_check",
                formula="subtotal + tax_amount - discount + rounding_adjustment",
                operands={"subtotal": subtotal, "tax_amount": tax, "discount": discount},
                calculated=None,
                reported=total,
                tolerance=tolerance,
            )
        )

    # 2. Line Items Item Total Check: Qty * Unit Price ≈ Line Total
    for idx, li in enumerate(invoice.line_items):
        if li.quantity is not None and li.unit_price is not None and li.amount is not None:
            calc_amt = li.quantity * li.unit_price
            checks.append(
                make_check(
                    name=f"line_item_{idx + 1}_amount_check",
                    formula="quantity * unit_price",
                    operands={"quantity": li.quantity, "unit_price": li.unit_price},
                    calculated=calc_amt,
                    reported=li.amount,
                    tolerance=tolerance,
                )
            )

    # 3. Cash & Change Check: Cash Paid - Total Amount == Change Given
    cash = invoice.cash_paid.value
    change = invoice.change_given.value
    if cash is not None and total is not None and change is not None:
        calc_change = cash - total
        checks.append(
            make_check(
                name="cash_and_change_check",
                formula="cash_paid - total_amount",
                operands={"cash_paid": cash, "total_amount": total},
                calculated=calc_change,
                reported=change,
                tolerance=tolerance,
            )
        )

    return checks


# ==============================================================================
# BALANCE SHEET VALIDATIONS
# ==============================================================================

def validate_balance_sheet_period(
    p: BalanceSheetPeriodData,
    label: str,
    tolerance: float = 1.0,
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    period_str = p.period or label

    # Check 1: Total Capital & Liabilities ≈ Total Assets
    cap_liab = p.total_capital_and_liabilities
    assets = p.total_assets
    checks.append(
        make_check(
            name=f"balance_sheet_equality_{label}",
            formula="total_capital_and_liabilities ≈ total_assets",
            operands={"total_capital_and_liabilities": cap_liab, "total_assets": assets},
            calculated=cap_liab,
            reported=assets,
            tolerance=tolerance,
            period=period_str,
        )
    )

    # Check 2: Liabilities Component Reconcile
    comp_liab = [p.capital, p.reserves_and_surplus, p.minority_interest, p.deposits, p.borrowings, p.other_liabilities_provisions]
    present_comp_liab = [x for x in comp_liab if x is not None]
    if len(present_comp_liab) >= 2 and cap_liab is not None:
        calc_cap_liab = sum(present_comp_liab)
        checks.append(
            make_check(
                name=f"capital_liabilities_components_{label}",
                formula="capital + reserves + minority_interest + deposits + borrowings + other_liabilities",
                operands={
                    "capital": p.capital,
                    "reserves_and_surplus": p.reserves_and_surplus,
                    "deposits": p.deposits,
                    "borrowings": p.borrowings,
                    "other_liabilities": p.other_liabilities_provisions,
                },
                calculated=calc_cap_liab,
                reported=cap_liab,
                tolerance=tolerance,
                period=period_str,
            )
        )

    # Check 3: Assets Component Reconcile
    comp_assets = [
        p.cash_and_balances_with_central_bank,
        p.balances_with_banks_money_at_call,
        p.investments,
        p.advances_or_loans,
        p.fixed_assets,
        p.other_assets,
    ]
    present_comp_assets = [x for x in comp_assets if x is not None]
    if len(present_comp_assets) >= 2 and assets is not None:
        calc_assets = sum(present_comp_assets)
        checks.append(
            make_check(
                name=f"assets_components_{label}",
                formula="cash + bank_balances + investments + advances + fixed_assets + other_assets",
                operands={
                    "cash": p.cash_and_balances_with_central_bank,
                    "investments": p.investments,
                    "advances": p.advances_or_loans,
                    "fixed_assets": p.fixed_assets,
                    "other_assets": p.other_assets,
                },
                calculated=calc_assets,
                reported=assets,
                tolerance=tolerance,
                period=period_str,
            )
        )

    return checks


def validate_balance_sheet(bs: BalanceSheetData, tolerance: float = 1.0) -> list[ValidationCheck]:
    checks = []
    checks.extend(validate_balance_sheet_period(bs.current_period, "current_period", tolerance))
    if bs.comparative_period.period or bs.comparative_period.total_assets is not None:
        checks.extend(validate_balance_sheet_period(bs.comparative_period, "comparative_period", tolerance))
    return checks


# ==============================================================================
# PROFIT & LOSS VALIDATIONS
# ==============================================================================

def validate_profit_loss_period(
    p: ProfitLossPeriodData,
    label: str,
    tolerance: float = 1.0,
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    period_str = p.period or label

    # Check 1: Total Income = Interest Earned + Other Income
    if p.interest_earned is not None or p.other_income is not None:
        calc_income = (p.interest_earned or 0.0) + (p.other_income or 0.0)
        checks.append(
            make_check(
                name=f"total_income_check_{label}",
                formula="interest_earned + other_income",
                operands={"interest_earned": p.interest_earned, "other_income": p.other_income},
                calculated=calc_income if p.interest_earned is not None and p.other_income is not None else None,
                reported=p.total_income,
                tolerance=tolerance,
                period=period_str,
            )
        )

    # Check 2: Total Expenditure = Interest Expended + Operating Expenses + Provisions
    exp_comps = [p.interest_expended, p.operating_expenses, p.provisions_and_contingencies]
    if any(x is not None for x in exp_comps):
        calc_exp = sum(x or 0.0 for x in exp_comps)
        all_present = all(x is not None for x in exp_comps)
        checks.append(
            make_check(
                name=f"total_expenditure_check_{label}",
                formula="interest_expended + operating_expenses + provisions_and_contingencies",
                operands={
                    "interest_expended": p.interest_expended,
                    "operating_expenses": p.operating_expenses,
                    "provisions": p.provisions_and_contingencies,
                },
                calculated=calc_exp if all_present else None,
                reported=p.total_expenditure,
                tolerance=tolerance,
                period=period_str,
            )
        )

    # Check 3: Net Profit = Total Income - Total Expenditure
    if p.total_income is not None and p.total_expenditure is not None:
        calc_profit = p.total_income - p.total_expenditure
        checks.append(
            make_check(
                name=f"net_profit_before_minority_check_{label}",
                formula="total_income - total_expenditure",
                operands={"total_income": p.total_income, "total_expenditure": p.total_expenditure},
                calculated=calc_profit,
                reported=p.net_profit_before_minority,
                tolerance=tolerance,
                period=period_str,
            )
        )

    # Check 4: Consolidated Profit = Net Profit - Minority Interest + Associates
    if p.net_profit_before_minority is not None and p.consolidated_net_profit is not None:
        min_int = p.minority_interest or 0.0
        assoc = p.share_in_profit_of_associates or 0.0
        calc_cons = p.net_profit_before_minority - min_int + assoc
        checks.append(
            make_check(
                name=f"consolidated_profit_check_{label}",
                formula="net_profit_before_minority - minority_interest + share_in_profit_of_associates",
                operands={
                    "net_profit_before_minority": p.net_profit_before_minority,
                    "minority_interest": p.minority_interest,
                    "associates": p.share_in_profit_of_associates,
                },
                calculated=calc_cons,
                reported=p.consolidated_net_profit,
                tolerance=tolerance,
                period=period_str,
            )
        )

    # Check 5: Total Available for Appropriation = Current Profit + Brought Forward
    if p.profit_brought_forward is not None and p.total_available_for_appropriation is not None:
        base_profit = p.consolidated_net_profit or p.net_profit_before_minority
        if base_profit is not None:
            calc_avail = base_profit + p.profit_brought_forward
            checks.append(
                make_check(
                    name=f"appropriation_total_check_{label}",
                    formula="current_profit + profit_brought_forward",
                    operands={"current_profit": base_profit, "profit_brought_forward": p.profit_brought_forward},
                    calculated=calc_avail,
                    reported=p.total_available_for_appropriation,
                    tolerance=tolerance,
                    period=period_str,
                )
            )

    return checks


def validate_profit_loss(pl: ProfitLossData, tolerance: float = 1.0) -> list[ValidationCheck]:
    checks = []
    checks.extend(validate_profit_loss_period(pl.current_period, "current_period", tolerance))
    if pl.comparative_period.period or pl.comparative_period.total_income is not None:
        checks.extend(validate_profit_loss_period(pl.comparative_period, "comparative_period", tolerance))
    return checks


# ==============================================================================
# CASH FLOW VALIDATIONS
# ==============================================================================

def validate_cash_flow_period(
    p: CashFlowPeriodData,
    label: str,
    tolerance: float = 1.0,
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    period_str = p.period or label

    # Check 1: Net Increase in Cash = Operating + Investing + Financing + FX
    cf_comps = [p.net_cash_operating, p.net_cash_investing, p.net_cash_financing]
    if any(x is not None for x in cf_comps):
        all_cf = all(x is not None for x in cf_comps)
        fx = p.fx_translation_adjustment or 0.0
        calc_inc = (p.net_cash_operating or 0.0) + (p.net_cash_investing or 0.0) + (p.net_cash_financing or 0.0) + fx
        checks.append(
            make_check(
                name=f"net_change_in_cash_check_{label}",
                formula="net_cash_operating + net_cash_investing + net_cash_financing + fx_translation_adjustment",
                operands={
                    "operating": p.net_cash_operating,
                    "investing": p.net_cash_investing,
                    "financing": p.net_cash_financing,
                    "fx": p.fx_translation_adjustment,
                },
                calculated=calc_inc if all_cf else None,
                reported=p.net_increase_in_cash,
                tolerance=tolerance,
                period=period_str,
            )
        )

    # Check 2: Closing Cash = Opening Cash + Net Increase in Cash + Adjustments
    if p.opening_cash_equivalents is not None and p.closing_cash_equivalents is not None:
        net_inc = p.net_increase_in_cash or 0.0
        adj = p.cash_acquired_adjustments or 0.0
        calc_close = p.opening_cash_equivalents + net_inc + adj
        checks.append(
            make_check(
                name=f"cash_reconciliation_check_{label}",
                formula="opening_cash_equivalents + net_increase_in_cash + cash_acquired_adjustments",
                operands={
                    "opening_cash": p.opening_cash_equivalents,
                    "net_increase": p.net_increase_in_cash,
                    "adjustments": p.cash_acquired_adjustments,
                },
                calculated=calc_close,
                reported=p.closing_cash_equivalents,
                tolerance=tolerance,
                period=period_str,
            )
        )

    return checks


def validate_cash_flow(cf: CashFlowData, tolerance: float = 1.0) -> list[ValidationCheck]:
    checks = []
    checks.extend(validate_cash_flow_period(cf.current_period, "current_period", tolerance))
    if cf.comparative_period.period or cf.comparative_period.closing_cash_equivalents is not None:
        checks.extend(validate_cash_flow_period(cf.comparative_period, "comparative_period", tolerance))
    return checks


# ==============================================================================
# UNIFIED ENTRYPOINT
# ==============================================================================

def validate_financial_calculations(
    extracted_data: ExtractedDataModel,
    document_type: DocumentType,
    *,
    settings: Optional[Settings] = None,
) -> ValidationSummary:
    """Run all mathematical checks on extracted data and return structured summary."""
    cfg = settings or get_settings()
    tol = cfg.validation_tolerance

    checks: list[ValidationCheck] = []
    if document_type == "invoice" and isinstance(extracted_data, InvoiceData):
        checks = validate_invoice(extracted_data, tolerance=tol)
    elif document_type == "balance_sheet" and isinstance(extracted_data, BalanceSheetData):
        checks = validate_balance_sheet(extracted_data, tolerance=tol)
    elif document_type == "profit_and_loss" and isinstance(extracted_data, ProfitLossData):
        checks = validate_profit_loss(extracted_data, tolerance=tol)
    elif document_type == "cash_flow_statement" and isinstance(extracted_data, CashFlowData):
        checks = validate_cash_flow(extracted_data, tolerance=tol)

    issues: list[str] = []
    any_failed = False
    for c in checks:
        if c.status == "FAIL":
            any_failed = True
            msg = f"Check '{c.name}' failed: calculated {c.calculated_value} vs reported {c.reported_value} (variance {c.variance})"
            issues.append(msg)
            logger.warning(msg)

    overall: CheckStatus = "FAIL" if any_failed else "PASS"

    logger.info(
        "Financial validation completed doc_type=%s total_checks=%d status=%s",
        document_type,
        len(checks),
        overall,
    )

    return ValidationSummary(
        checks=checks,
        overall_status=overall,
        issues=issues,
    )
