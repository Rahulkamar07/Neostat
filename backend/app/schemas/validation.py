"""Validation schemas for financial checks and calculation verification.

Adheres directly to Section 4.4 and Section 5.2 of the case study specification:
Each check contains:
- name: check identifier
- formula: string description of the mathematical check
- operands: input values used in calculation
- calculated_value: mathematically computed result
- reported_value: value declared in the source document
- variance: absolute difference |calculated - reported|
- status: PASS | FAIL | NOT_APPLICABLE
"""

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

CheckStatus = Literal["PASS", "FAIL", "NOT_APPLICABLE"]


class ValidationCheck(BaseModel):
    """Result of a single financial validation check."""

    name: str = Field(..., description="Machine-readable name of the validation check")
    formula: str = Field(..., description="Human-readable formula used for validation")
    operands: dict[str, Optional[float]] = Field(
        default_factory=dict, description="Dictionary of actual input values used"
    )
    calculated_value: Optional[float] = Field(
        None, description="Value computed by applying the formula to the operands"
    )
    reported_value: Optional[float] = Field(
        None, description="Target value reported in the source document"
    )
    variance: Optional[float] = Field(
        None, description="Absolute difference between calculated_value and reported_value"
    )
    status: CheckStatus = Field(..., description="Validation outcome: PASS, FAIL, or NOT_APPLICABLE")
    period: Optional[str] = Field(None, description="Associated period if comparative (e.g. '31-Mar-17')")


class ValidationSummary(BaseModel):
    """Aggregate result across all financial checks for a document."""

    checks: list[ValidationCheck] = Field(default_factory=list)
    overall_status: CheckStatus = Field(
        "PASS", description="Overall validation status: PASS if all applicable pass, FAIL if any fail"
    )
    issues: list[str] = Field(default_factory=list, description="Summary of any validation discrepancies")
