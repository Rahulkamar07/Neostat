"""Tests for Phase 5: Financial calculation validation service.

Covers:
1. Invoice calculations:
   - PASS case: subtotal + tax - discount + rounding = total
   - FAIL case: deliberate mismatch in total
   - NOT_APPLICABLE case: missing subtotal / operands
2. Balance Sheet validations:
   - PASS case: total capital & liabilities ≈ total assets
   - FAIL case: mismatched totals
   - NOT_APPLICABLE case: missing required totals
3. Profit & Loss checks (income, expenditure, net profit).
4. Cash Flow checks (operating + investing + financing = net change, opening + net change = closing).
5. Comparative-period independent validation.
"""

import pytest

from app.schemas.extraction import (
    BalanceSheetData,
    BalanceSheetPeriodData,
    CashFlowData,
    CashFlowPeriodData,
    InvoiceData,
    InvoiceLineItem,
    ProfitLossData,
    ProfitLossPeriodData,
)
from app.services.financial_validation_service import validate_financial_calculations


# ==============================================================================
# INVOICE TESTS
# ==============================================================================

def test_invoice_validation_pass():
    """Verify clean PASS for invoice where subtotal + tax - discount = total."""
    invoice = InvoiceData(
        subtotal={"value": 100.0},
        tax_amount={"value": 10.0},
        discount={"value": 5.0},
        total_amount={"value": 105.0},
        cash_paid={"value": 150.0},
        change_given={"value": 45.0},
        line_items=[
            InvoiceLineItem(description="Item A", quantity=2.0, unit_price=50.0, amount=100.0)
        ],
    )

    summary = validate_financial_calculations(invoice, "invoice")
    assert summary.overall_status == "PASS"
    assert len(summary.issues) == 0

    total_chk = next(c for c in summary.checks if c.name == "invoice_total_check")
    assert total_chk.status == "PASS"
    assert total_chk.calculated_value == 105.0
    assert total_chk.variance == 0.0

    li_chk = next(c for c in summary.checks if "line_item_1" in c.name)
    assert li_chk.status == "PASS"
    assert li_chk.calculated_value == 100.0


def test_invoice_validation_deliberate_fail():
    """Verify deliberate FAIL when reported total diverges from math."""
    invoice = InvoiceData(
        subtotal={"value": 100.0},
        tax_amount={"value": 10.0},
        discount={"value": 0.0},
        total_amount={"value": 999.0},  # Deliberate mismatch
    )

    summary = validate_financial_calculations(invoice, "invoice")
    assert summary.overall_status == "FAIL"
    assert len(summary.issues) > 0

    total_chk = next(c for c in summary.checks if c.name == "invoice_total_check")
    assert total_chk.status == "FAIL"
    assert total_chk.calculated_value == 110.0
    assert total_chk.reported_value == 999.0
    assert total_chk.variance == 889.0


def test_invoice_validation_not_applicable():
    """Verify NOT_APPLICABLE when required fields are null (no guessing)."""
    invoice = InvoiceData(
        subtotal={"value": None},
        total_amount={"value": 100.0},
    )

    summary = validate_financial_calculations(invoice, "invoice")
    total_chk = next(c for c in summary.checks if c.name == "invoice_total_check")
    assert total_chk.status == "NOT_APPLICABLE"
    assert total_chk.calculated_value is None


# ==============================================================================
# BALANCE SHEET TESTS
# ==============================================================================

def test_balance_sheet_validation_pass():
    """Verify balance sheet equality passes for current and comparative periods."""
    bs = BalanceSheetData(
        current_period=BalanceSheetPeriodData(
            period="31-Mar-17",
            capital=100.0,
            reserves_and_surplus=900.0,
            total_capital_and_liabilities=1000.0,
            total_assets=1000.0,
        ),
        comparative_period=BalanceSheetPeriodData(
            period="31-Mar-16",
            total_capital_and_liabilities=850.0,
            total_assets=850.0,
        ),
    )

    summary = validate_financial_calculations(bs, "balance_sheet")
    assert summary.overall_status == "PASS"

    cur_eq = next(c for c in summary.checks if c.name == "balance_sheet_equality_current_period")
    assert cur_eq.status == "PASS"
    assert cur_eq.variance == 0.0

    comp_eq = next(c for c in summary.checks if c.name == "balance_sheet_equality_comparative_period")
    assert comp_eq.status == "PASS"


def test_balance_sheet_validation_fail():
    """Verify FAIL when assets and liabilities do not balance."""
    bs = BalanceSheetData(
        current_period=BalanceSheetPeriodData(
            total_capital_and_liabilities=1000.0,
            total_assets=950.0,  # 50.0 variance
        )
    )

    summary = validate_financial_calculations(bs, "balance_sheet")
    assert summary.overall_status == "FAIL"

    cur_eq = next(c for c in summary.checks if c.name == "balance_sheet_equality_current_period")
    assert cur_eq.status == "FAIL"
    assert cur_eq.variance == 50.0


def test_balance_sheet_validation_not_applicable():
    """Verify NOT_APPLICABLE when totals are missing."""
    bs = BalanceSheetData(
        current_period=BalanceSheetPeriodData(
            total_capital_and_liabilities=None,
            total_assets=1000.0,
        )
    )

    summary = validate_financial_calculations(bs, "balance_sheet")
    cur_eq = next(c for c in summary.checks if c.name == "balance_sheet_equality_current_period")
    assert cur_eq.status == "NOT_APPLICABLE"


# ==============================================================================
# PROFIT & LOSS TESTS
# ==============================================================================

def test_profit_loss_validation():
    """Verify income, expenditure, and net profit checks."""
    pl = ProfitLossData(
        current_period=ProfitLossPeriodData(
            period="31-Mar-17",
            interest_earned=700.0,
            other_income=100.0,
            total_income=800.0,
            interest_expended=300.0,
            operating_expenses=200.0,
            provisions_and_contingencies=100.0,
            total_expenditure=600.0,
            net_profit_before_minority=200.0,
            minority_interest=10.0,
            consolidated_net_profit=190.0,
        )
    )

    summary = validate_financial_calculations(pl, "profit_and_loss")
    assert summary.overall_status == "PASS"

    inc_chk = next(c for c in summary.checks if "total_income" in c.name)
    assert inc_chk.status == "PASS"
    assert inc_chk.calculated_value == 800.0

    exp_chk = next(c for c in summary.checks if "total_expenditure" in c.name)
    assert exp_chk.status == "PASS"
    assert exp_chk.calculated_value == 600.0

    profit_chk = next(c for c in summary.checks if "net_profit_before_minority" in c.name)
    assert profit_chk.status == "PASS"
    assert profit_chk.calculated_value == 200.0


# ==============================================================================
# CASH FLOW TESTS
# ==============================================================================

def test_cash_flow_validation():
    """Verify cash reconciliation with negative numbers."""
    cf = CashFlowData(
        current_period=CashFlowPeriodData(
            net_cash_operating=150.0,
            net_cash_investing=-50.0,
            net_cash_financing=-20.0,
            fx_translation_adjustment=0.0,
            net_increase_in_cash=80.0,
            opening_cash_equivalents=200.0,
            cash_acquired_adjustments=0.0,
            closing_cash_equivalents=280.0,
        )
    )

    summary = validate_financial_calculations(cf, "cash_flow_statement")
    assert summary.overall_status == "PASS"

    cf_inc = next(c for c in summary.checks if "net_change_in_cash" in c.name)
    assert cf_inc.status == "PASS"
    assert cf_inc.calculated_value == 80.0

    close_chk = next(c for c in summary.checks if "cash_reconciliation" in c.name)
    assert close_chk.status == "PASS"
    assert close_chk.calculated_value == 280.0
