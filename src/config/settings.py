"""
Task: CFG-001 - Configuration & Tolerance Settings Management
Description: Centralized configuration management using Pydantic.
PRD Section: 3.2 Tolerances (defaults + configurable)

Settings are loaded in this priority order:
1. .env file in project root (if present)
2. Environment variables (e.g. AMOUNT_MATCH_TOLERANCE_INR=5.0)
3. Default values defined below
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Dict


class Settings(BaseSettings):
    """
    Application-wide configuration settings and tolerances.

    All fields can be overridden via environment variables or a .env file.
    Variable names are case-insensitive (e.g. AMOUNT_MATCH_TOLERANCE_INR=5.0).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unknown env vars
    )

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
    late_payment_threshold_days: int = Field(0, description="Days after delivery before flagging as late payment")

    # Payment Mode Mapping (PRD 2.1)
    # Note: In runner notepad, staff mark both GPay and Paytm as "Online".
    # Notepad payment mode is ONLY used for cash-vs-noncash classification
    # (for cash variance detection). CRM is the authoritative source for payment mode.
    payment_mode_mapping: Dict[str, str] = Field(default_factory=lambda: {
        "cash": "Cash",
        "gpay": "GPay",
        "google pay": "GPay",
        "upi": "GPay",
        "paytm": "Paytm",
        "package": "Package",
        "online": "Online",  # Notepad generic: could be GPay or Paytm
        "noncash": "Online",
        "card": "Card",
        "due": "Due",          # Payment pending — delivered but not paid
        "adv": "Advance",      # Advance payment received
        "advance": "Advance",
        "adv paid": "Advance",
        "adv payment": "Advance",
    })

    # ── Property Aliases for service-level access ──────────
    @property
    def amount_tolerance(self) -> float:
        return self.amount_match_tolerance_inr

    @property
    def fuzzy_name_threshold(self) -> float:
        return self.fuzzy_name_min_score

    @property
    def date_window_days(self) -> int:
        return self.fuzzy_date_proximity_days

    @property
    def cash_variance_tolerance(self) -> float:
        return self.cash_variance_tolerance_inr

    @property
    def gpay_tolerance(self) -> float:
        return self.daily_total_tolerance_inr

    @property
    def credit_tolerance(self) -> float:
        return self.credit_tolerance_inr

    @property
    def confidence_auto_accept(self) -> float:
        return 0.85

    @property
    def confidence_review_threshold(self) -> float:
        return 0.60


settings = Settings()
