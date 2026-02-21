"""
Task: CFG-001 - Configuration & Tolerance Settings Management
Description: Centralized configuration management using Pydantic.
PRD Section: 3.2 Tolerances (defaults + configurable)
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict

class Settings(BaseModel):
    """
    Application-wide configuration settings and tolerances.

    This class defines the default values for all tunable parameters in the system.
    It uses Pydantic for validation and type safety.
    These settings can be overridden by environment variables or database entries.

    Attributes:
        amount_match_tolerance_inr: Max difference to consider amounts a match (PRD 3.2).
        daily_total_tolerance_inr: Absolute tolerance for day-level comparisons.
        daily_total_tolerance_percent: Percentage tolerance for day-level comparisons.
        mswipe_time_match_window_minutes: Time window for linking MSWIPE txns to orders.
        fuzzy_name_min_score: Minimum similarity score (0-1) for fuzzy name matching.
        fuzzy_date_proximity_days: Max days difference for fuzzy date matching.
        cash_variance_tolerance_inr: Absolute tolerance for cash register variance.
        cash_variance_tolerance_percent: Percentage tolerance for cash register variance.
        credit_tolerance_inr: Max outstanding balance before flagging credit violation (PRD 3.8).
        payment_mode_mapping: Dictionary normalizing source payment modes to internal types.
    """

    # Tolerances (PRD 3.2)
    amount_match_tolerance_inr: float = Field(2.0, description="Order-level amount match tolerance")
    daily_total_tolerance_inr: float = Field(10.0, description="Day-level comparisons tolerance INR")
    daily_total_tolerance_percent: float = Field(0.5, description="Day-level comparisons tolerance Percent")
    mswipe_time_match_window_minutes: int = Field(180, description="MSWIPE time match window")
    fuzzy_name_min_score: float = Field(0.82, description="Fuzzy name match min score")
    fuzzy_date_proximity_days: int = Field(3, description="Fuzzy date proximity days")
    cash_variance_tolerance_inr: float = Field(100.0, description="Cash variance tolerance INR")
    cash_variance_tolerance_percent: float = Field(1.0, description="Cash variance tolerance Percent")
    credit_tolerance_inr: float = Field(1.0, description="Credit tolerance INR")

    # Payment Mode Mapping (PRD 2.1)
    # Normalizes varied input strings (e.g. 'google pay', 'upi') to standard internal keys.
    payment_mode_mapping: Dict[str, str] = Field(default_factory=lambda: {
        "cash": "Cash",
        "gpay": "GPay",
        "google pay": "GPay",
        "upi": "GPay",
        "paytm": "Paytm",
        "online": "Online",
        "card": "Card"
    })

    class Config:
        arbitrary_types_allowed = True

settings = Settings()
