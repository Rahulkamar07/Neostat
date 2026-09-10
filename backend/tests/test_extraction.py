"""Tests for Phase 4: Pydantic schemas and structured extraction module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.exceptions import LLMConfigurationError, LLMExtractionError
from app.schemas.extraction import (
    BalanceSheetData,
    CashFlowData,
    InvoiceData,
    InvoiceLineItem,
    ProfitLossData,
)
from app.schemas.ocr import DocumentTextResult, PageTextResult
from app.services.extraction_service import (
    extract_structured_data,
    extract_with_gemini,
    extract_with_openai,
)


@pytest.fixture
def mock_invoice_text_result() -> DocumentTextResult:
    return DocumentTextResult(
        pages=[
            PageTextResult(
                page_number=1,
                text=(
                    "INDAH GIFT & HOME DECO\n"
                    "RECEIPT #01\n"
                    "19/10/2018\n"
                    "Desc/Item Qty Price Amt(RM)\n"
                    "ST-PRIVILEGE CARD 1 10.00 10.00\n"
                    "GF-TABLELAMP 1 55.90 55.90\n"
                    "@DISC 10.00% -5.59\n"
                    "TOTAL AMT. RM 60.31\n"
                    "CASH RM 100.00\n"
                    "CHANGE RM 39.69\n"
                ),
                extraction_method="ocr",
                char_count=250,
            )
        ],
        total_pages=1,
        ocr_used=True,
        total_characters=250,
    )


@pytest.fixture
def sample_invoice_dict() -> dict:
    return {
        "invoice_number": {"value": "#01", "page_number": 1, "source_text": "RECEIPT #01"},
        "invoice_date": {"value": "2018-10-19", "page_number": 1, "source_text": "19/10/2018"},
        "vendor_name": {"value": "INDAH GIFT & HOME DECO", "page_number": 1, "source_text": "INDAH GIFT & HOME DECO"},
        "currency": {"value": "RM", "page_number": 1, "source_text": "RM"},
        "subtotal": {"value": 65.90, "page_number": 1, "source_text": "10.00 + 55.90"},
        "tax_amount": {"value": 0.0, "page_number": 1, "source_text": None},
        "discount": {"value": 5.59, "page_number": 1, "source_text": "@DISC 10.00% -5.59"},
        "total_amount": {"value": 60.31, "page_number": 1, "source_text": "TOTAL AMT. RM 60.31"},
        "cash_paid": {"value": 100.00, "page_number": 1, "source_text": "CASH RM 100.00"},
        "change_given": {"value": 39.69, "page_number": 1, "source_text": "CHANGE RM 39.69"},
        "line_items": [
            {"description": "ST-PRIVILEGE CARD", "quantity": 1.0, "unit_price": 10.00, "amount": 10.00, "page_number": 1},
            {"description": "GF-TABLELAMP", "quantity": 1.0, "unit_price": 55.90, "amount": 55.90, "page_number": 1},
        ],
    }


def test_invoice_schema_validation(sample_invoice_dict: dict):
    """Verify InvoiceData parses and validates correctly with grounded fields."""
    invoice = InvoiceData.model_validate(sample_invoice_dict)

    assert invoice.invoice_number.value == "#01"
    assert invoice.invoice_number.evidence.source_text == "RECEIPT #01"
    assert invoice.total_amount.value == 60.31
    assert len(invoice.line_items) == 2
    assert invoice.line_items[0].description == "ST-PRIVILEGE CARD"
    assert invoice.line_items[1].amount == 55.90


def test_balance_sheet_schema_validation():
    """Verify BalanceSheetData structure with current and comparative period data."""
    bs_data = {
        "header": {
            "company_name": {"value": "Acme Bank"},
            "currency": {"value": "INR"},
            "unit_multiplier": {"value": "in thousands"},
            "reporting_period": {"value": "31-Mar-17"},
            "comparative_period": {"value": "31-Mar-16"},
        },
        "current_period": {
            "period": "31-Mar-17",
            "capital": 5125091.0,
            "reserves_and_surplus": 912814397.0,
            "total_capital_and_liabilities": 8923441607.0,
            "total_assets": 8923441607.0,
        },
        "comparative_period": {
            "period": "31-Mar-16",
            "capital": 5056373.0,
            "reserves_and_surplus": 737984869.0,
            "total_capital_and_liabilities": 7622123264.0,
            "total_assets": 7622123264.0,
        },
        "line_items": [
            {
                "line_item_name": "Capital",
                "schedule_number": "1",
                "current_value": 5125091.0,
                "comparative_value": 5056373.0,
            }
        ],
    }
    bs = BalanceSheetData.model_validate(bs_data)
    assert bs.header.company_name.value == "Acme Bank"
    assert bs.current_period.total_assets == 8923441607.0
    assert bs.comparative_period.total_capital_and_liabilities == 7622123264.0
    assert len(bs.line_items) == 1


def test_profit_loss_schema_validation():
    """Verify ProfitLossData structure parses correctly."""
    pl_data = {
        "header": {"company_name": {"value": "Acme Corp"}, "currency": {"value": "INR"}},
        "current_period": {
            "interest_earned": 732713529.0,
            "other_income": 128776329.0,
            "total_income": 861489858.0,
            "interest_expended": 380415844.0,
            "operating_expenses": 207510707.0,
            "provisions_and_contingencies": 120689285.0,
            "total_expenditure": 708615836.0,
            "consolidated_net_profit": 152530250.0,
        },
    }
    pl = ProfitLossData.model_validate(pl_data)
    assert pl.current_period.total_income == 861489858.0
    assert pl.current_period.total_expenditure == 708615836.0


def test_cash_flow_schema_validation():
    """Verify CashFlowData negative values and structure."""
    cf_data = {
        "header": {"statement_title": {"value": "Consolidated Cash Flow"}},
        "current_period": {
            "profit_before_tax": 233311478.0,
            "net_cash_operating": 172815931.0,
            "net_cash_investing": -84347716.0,
            "net_cash_financing": -88468215.0,
            "net_increase_in_cash": 0.0,
            "opening_cash_equivalents": 300765846.0,
            "closing_cash_equivalents": 379105485.0,
        },
    }
    cf = CashFlowData.model_validate(cf_data)
    assert cf.current_period.net_cash_investing == -84347716.0


def test_extraction_missing_api_key_raises_configuration_error(mock_invoice_text_result):
    """When no API key is provided, LLMConfigurationError is raised."""
    settings = Settings(llm_provider="gemini", gemini_api_key="")
    with pytest.raises(LLMConfigurationError) as exc_info:
        extract_structured_data(mock_invoice_text_result, "invoice", settings=settings)
    assert exc_info.value.code == "LLM_NOT_CONFIGURED"


@patch("app.services.extraction_service.extract_with_gemini")
def test_extract_structured_data_invokes_gemini_and_validates(
    mock_gemini, mock_invoice_text_result, sample_invoice_dict
):
    """When Gemini is configured, it calls the Gemini extraction path and validates against Pydantic."""
    mock_gemini.return_value = sample_invoice_dict
    settings = Settings(llm_provider="gemini", gemini_api_key="fake-test-key")

    result = extract_structured_data(mock_invoice_text_result, "invoice", settings=settings)

    assert isinstance(result, InvoiceData)
    assert result.total_amount.value == 60.31
    mock_gemini.assert_called_once()
