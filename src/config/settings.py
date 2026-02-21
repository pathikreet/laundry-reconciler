from pydantic import BaseModel, Field
from typing import Optional, Dict

class Settings(BaseModel):
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

    # Payment Mode Mapping
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
