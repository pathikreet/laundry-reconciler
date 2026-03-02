"""
Custom exception classes for the Laundry Reconciler application.
Provides clear, user-friendly error messages with context about
what went wrong, where (file/row/column), and how to fix it.
"""


class LaundryReconcilerError(Exception):
    """Base exception for all Laundry Reconciler errors."""
    def __init__(self, message: str, details: dict = None):
        self.details = details or {}
        super().__init__(message)


# ── Import Errors ─────────────────────────────────────────────

class ImportError(LaundryReconcilerError):
    """Base class for all import-related errors."""
    pass


class FileValidationError(ImportError):
    """Raised when a file fails validation (wrong type, too large, unreadable)."""
    def __init__(self, file_path: str, reason: str):
        super().__init__(
            f"File validation failed for '{file_path}': {reason}",
            details={"file_path": file_path, "reason": reason}
        )


class MissingColumnsError(ImportError):
    """Raised when required columns are missing from an import file."""
    def __init__(self, file_path: str, missing: list, available: list = None):
        cols = ", ".join(missing)
        msg = f"Missing required columns in '{file_path}': {cols}"
        if available:
            msg += f". Available columns: {', '.join(available)}"
        super().__init__(
            msg,
            details={"file_path": file_path, "missing_columns": missing, "available_columns": available}
        )


class InvalidDataError(ImportError):
    """Raised when a row contains invalid data (bad dates, amounts, etc.)."""
    def __init__(self, file_path: str, row: int, column: str, value: str, expected: str):
        super().__init__(
            f"Invalid data in '{file_path}' at row {row}, column '{column}': "
            f"got '{value}', expected {expected}",
            details={
                "file_path": file_path, "row": row,
                "column": column, "value": value, "expected": expected
            }
        )


class UnmappedPaymentModeError(ImportError):
    """Raised when a payment mode cannot be mapped to a known mode."""
    def __init__(self, mode: str, known_modes: list):
        super().__init__(
            f"Unknown payment mode '{mode}'. Known modes: {', '.join(known_modes)}. "
            f"Please update payment mode mappings in settings.",
            details={"mode": mode, "known_modes": known_modes}
        )


# ── Matching Errors ───────────────────────────────────────────

class MatchingError(LaundryReconcilerError):
    """Base class for matching-related errors."""
    pass


class NoMatchFoundError(MatchingError):
    """Raised when no match can be found for a record."""
    pass


class AmbiguousMatchError(MatchingError):
    """Raised when multiple candidates have similar confidence scores."""
    def __init__(self, record_id: str, candidates: list):
        super().__init__(
            f"Ambiguous match for record '{record_id}': "
            f"{len(candidates)} candidates with similar scores",
            details={"record_id": record_id, "candidates": candidates}
        )


# ── Reconciliation Errors ────────────────────────────────────

class ReconciliationError(LaundryReconcilerError):
    """Base class for reconciliation-related errors."""
    pass


class DatabaseError(LaundryReconcilerError):
    """Raised for database-related errors."""
    pass


class ConfigurationError(LaundryReconcilerError):
    """Raised for configuration/settings errors."""
    pass


class ExportError(LaundryReconcilerError):
    """Raised when export generation fails."""
    pass
