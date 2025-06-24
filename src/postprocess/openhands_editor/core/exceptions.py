class LLMEditorError(Exception):
    """Base exception for LLM editor errors."""
    pass


class FunctionCallValidationError(LLMEditorError):
    """Raised when function call validation fails."""
    pass


class FunctionCallNotExistsError(LLMEditorError):
    """Raised when a requested function call does not exist."""
    pass


class FileEditError(LLMEditorError):
    """Raised when file editing operations fail."""
    pass


class ParameterValidationError(LLMEditorError):
    """Raised when parameter validation fails."""
    pass