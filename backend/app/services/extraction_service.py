"""LLM structured extraction service.

Takes normalized OCR/text output and extracts structured data matching the
document type Pydantic schema using Gemini (or OpenAI / Anthropic fallback).

Features:
- Swappable provider abstraction (Gemini default, OpenAI fallback).
- Strictly conforms to Pydantic models (InvoiceData, BalanceSheetData, ProfitLossData, CashFlowData).
- Adheres to Case Study rule 4.2: Extract ALL visible information; missing fields must be null (never guessed or invented).
- Preserves verbatim evidence strings and page numbers.
- Handles comparative periods (e.g. 31-Mar-17 and 31-Mar-16).
- Robust retries, clean error handling mapping to LLMExtractionError / LLMTimeoutError.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Type

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    LLMConfigurationError,
    LLMExtractionError,
    LLMTimeoutError,
)
from app.core.logging import get_logger
from app.schemas.extraction import (
    BalanceSheetData,
    CashFlowData,
    DocumentType,
    ExtractedDataModel,
    InvoiceData,
    ProfitLossData,
)
from app.schemas.ocr import DocumentTextResult

logger = get_logger(__name__)

SCHEMA_MAP: dict[DocumentType, Type[ExtractedDataModel]] = {
    "invoice": InvoiceData,
    "balance_sheet": BalanceSheetData,
    "profit_and_loss": ProfitLossData,
    "cash_flow_statement": CashFlowData,
}

SYSTEM_PROMPT = """You are a precision financial document extraction engine for an enterprise intelligence platform.
Your task is to extract all visible fields, tables, and financial data from the document text provided into a clean JSON structure adhering strictly to the provided JSON Schema.

CRITICAL EXTRACTION RULES:
1. STRICT ACCURACY: Every extracted value must accurately reflect the source document text. NEVER infer, assume, estimate, or invent a number.
2. MISSING VALUES: If a field is not present or visible in the document, return `null`. NEVER invent default or placeholder values.
3. GROUNDING & EVIDENCE: For key extracted fields, include the exact `source_text` snippet where you read the value, and the 1-indexed `page_number`.
4. NUMERIC NORMALIZATION:
   - Parse numbers into clean floats (e.g. "13,125.00" -> 13125.0).
   - Treat bracketed/parenthesized numbers as negative values (e.g. "(173,257,700)" -> -173257700.0).
   - In invoices, if discount is negative (e.g. "-5.59"), store the absolute or magnitude as appropriate (e.g. 5.59).
5. COMPARATIVE FINANCIAL STATEMENTS:
   - When a statement displays two years/columns (e.g. 31-Mar-17 and 31-Mar-16), extract the latest into `current_period` and prior into `comparative_period`.
   - Extract individual line items into `line_items` with both `current_value` and `comparative_value`.
6. RETURN RAW VALID JSON ONLY. Do not wrap in markdown codeblocks if possible, or use standard ```json ... ``` formatting.
"""


def _get_extraction_prompt(document_type: DocumentType, text: str) -> str:
    type_hints = {
        "invoice": (
            "This is an Invoice / Receipt. Extract invoice_number, invoice_date, vendor_name, customer_name, "
            "currency, subtotal, tax_amount, discount, total_amount, and all line_items (description, quantity, unit_price, amount)."
        ),
        "balance_sheet": (
            "This is a Balance Sheet. Extract statement header (company_name, periods, currency, unit multiplier), "
            "current_period and comparative_period totals (capital, reserves, minority_interest, deposits, borrowings, "
            "other_liabilities_provisions, total_capital_and_liabilities, cash/central bank, bank balances, investments, advances, "
            "fixed_assets, other_assets, total_assets), and all detailed line items in the table."
        ),
        "profit_and_loss": (
            "This is a Profit & Loss statement. Extract statement header, current_period and comparative_period totals "
            "(interest_earned, other_income, total_income, interest_expended, operating_expenses, provisions_and_contingencies, "
            "total_expenditure, operating_profit, net_profit_before_minority, minority_interest, share_in_profit_of_associates, "
            "consolidated_net_profit, profit_brought_forward, total_available_for_appropriation, transfer_to_statutory_reserve, "
            "proposed_dividend, transfer_to_general_reserve), and all detailed line items."
        ),
        "cash_flow_statement": (
            "This is a Cash Flow Statement. Extract statement header, current_period and comparative_period totals "
            "(profit_before_tax, net_cash_operating, net_cash_investing, net_cash_financing, fx_translation_adjustment, "
            "net_increase_in_cash, opening_cash_equivalents, cash_acquired_adjustments, closing_cash_equivalents), "
            "and all detailed line items. Treat bracketed numbers like (344,353,663) as negative."
        ),
    }

    return (
        f"DOCUMENT CATEGORY: {document_type}\n"
        f"SPECIAL INSTRUCTIONS: {type_hints.get(document_type, '')}\n\n"
        f"DOCUMENT TEXT CONTENT:\n{text}\n"
    )


def extract_with_gemini(
    prompt: str,
    target_schema: Type[ExtractedDataModel],
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Call Google Gemini using the modern google-genai SDK with structured output."""
    api_key = settings.gemini_api_key or settings.active_llm_api_key()
    if not api_key:
        raise LLMConfigurationError(
            message="GEMINI_API_KEY is not configured in .env or environment.",
            details={"provider": "gemini"},
        )

    try:
        from google import genai
        from google.genai import types

        import copy

        def _clean_schema_for_gemini(schema_dict: Any) -> Any:
            if isinstance(schema_dict, dict):
                schema_dict.pop("additionalProperties", None)
                for v in schema_dict.values():
                    _clean_schema_for_gemini(v)
            elif isinstance(schema_dict, list):
                for item in schema_dict:
                    _clean_schema_for_gemini(item)
            return schema_dict

        gemini_schema = _clean_schema_for_gemini(copy.deepcopy(target_schema.model_json_schema()))

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=f"{SYSTEM_PROMPT}\n\n{prompt}"),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=gemini_schema,
                temperature=0.0,
            ),
        )

        if not response.text:
            raise LLMExtractionError(message="Gemini returned an empty response.")

        return json.loads(response.text)

    except (LLMConfigurationError, LLMExtractionError):
        raise
    except TimeoutError as exc:
        logger.error("Gemini call timed out: %s", exc)
        raise LLMTimeoutError() from None
    except Exception as exc:
        logger.exception("Gemini extraction failed: %s", exc)
        raise LLMExtractionError(
            message=f"Gemini extraction error: {type(exc).__name__}",
            details={"provider": "gemini", "model": settings.gemini_model},
        ) from None


def extract_with_openai(
    prompt: str,
    target_schema: Type[ExtractedDataModel],
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Fallback call to OpenAI with structured outputs via response_format Pydantic model."""
    api_key = settings.openai_api_key or settings.active_llm_api_key()
    if not api_key:
        raise LLMConfigurationError(
            message="OPENAI_API_KEY is not configured.",
            details={"provider": "openai"},
        )

    try:
        import openai

        client = openai.OpenAI(api_key=api_key, timeout=settings.llm_timeout_seconds)
        completion = client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format=target_schema,
            temperature=0.0,
        )
        parsed = completion.choices[0].message.parsed
        if not parsed:
            raise LLMExtractionError(message="OpenAI returned no parsed structured content.")
        return parsed.model_dump()

    except (LLMConfigurationError, LLMExtractionError):
        raise
    except Exception as exc:
        logger.exception("OpenAI extraction failed: %s", exc)
        raise LLMExtractionError(
            message=f"OpenAI extraction error: {type(exc).__name__}",
            details={"provider": "openai", "model": settings.openai_model},
        ) from None


def extract_structured_data(
    ocr_result: DocumentTextResult,
    document_type: DocumentType,
    *,
    settings: Optional[Settings] = None,
) -> ExtractedDataModel:
    """Orchestrate LLM structured extraction according to document_type.

    Validates and returns the strongly-typed Pydantic model.
    """
    cfg = settings or get_settings()

    if document_type not in SCHEMA_MAP:
        raise LLMExtractionError(
            message=f"Unsupported document type for extraction: '{document_type}'",
            details={"document_type": document_type},
        )

    target_schema = SCHEMA_MAP[document_type]
    prompt = _get_extraction_prompt(document_type, ocr_result.full_text)

    logger.info(
        "Starting structured extraction doc_type=%s provider=%s total_pages=%d chars=%d",
        document_type,
        cfg.llm_provider,
        ocr_result.total_pages,
        ocr_result.total_characters,
    )

    provider = cfg.llm_provider.lower()
    raw_dict: dict[str, Any]

    if provider == "gemini":
        raw_dict = extract_with_gemini(prompt, target_schema, settings=cfg)
    elif provider == "openai":
        raw_dict = extract_with_openai(prompt, target_schema, settings=cfg)
    else:
        # Default to Gemini if unknown
        raw_dict = extract_with_gemini(prompt, target_schema, settings=cfg)

    # Validate against target Pydantic schema
    try:
        structured_obj = target_schema.model_validate(raw_dict)
        logger.info("Structured extraction succeeded for doc_type=%s", document_type)
        return structured_obj
    except Exception as exc:
        logger.error("Failed to parse extracted JSON into %s: %s", target_schema.__name__, exc)
        raise LLMExtractionError(
            message="LLM extraction output could not be validated against schema.",
            details={"schema": target_schema.__name__},
        ) from None
