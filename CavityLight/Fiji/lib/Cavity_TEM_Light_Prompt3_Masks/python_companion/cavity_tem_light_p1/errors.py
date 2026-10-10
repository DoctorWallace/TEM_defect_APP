"""Structured fail-closed errors shared by the Prompt-1 core."""


class Prompt1Error(Exception):
    """Base class for structured Prompt-1 failures."""

    code = "PROMPT1_ERROR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ContractError(Prompt1Error):
    code = "BLOCKED_INPUT_CONTRACT"


class ValidationError(Prompt1Error):
    code = "VALIDATION_FAILED"


class UnsafePathError(ValidationError):
    code = "UNSAFE_PATH"


class TransactionError(Prompt1Error):
    code = "TRANSACTION_FAILED"


class RecoveryBlocked(TransactionError):
    code = "RECOVERY_BLOCKED"


class StaleContextError(Prompt1Error):
    code = "STALE_CONTEXT_CANCELLED"


class EnvironmentBlocked(Prompt1Error):
    code = "BLOCKED_BY_ENVIRONMENT"

