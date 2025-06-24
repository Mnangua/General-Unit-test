"""Event and observation definitions for the standalone LLM editor."""

from dataclasses import dataclass
from typing import Optional, Any
from enum import Enum


@dataclass
class Observation:
    """Base class for all observations."""
    content: str = ""
    
    def __str__(self) -> str:
        return self.content


@dataclass
class FileEditObservation(Observation):
    """Observation from file editing operations."""
    
    path: str = ""
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    impl_source: Optional[str] = None
    diff: Optional[str] = None
    prev_exist: bool = False
    
    def __str__(self) -> str:
        if self.diff:
            return f"File {self.path} edited successfully.\n{self.diff}"
        return f"File {self.path} edited successfully.\n{self.content}"


@dataclass
class FileReadObservation(Observation):
    """Observation from file reading operations."""
    
    path: str = ""
    impl_source: Optional[str] = None
    
    def __str__(self) -> str:
        return f"Content of {self.path}:\n{self.content}"


@dataclass
class ErrorObservation(Observation):
    """Observation for error conditions."""
    
    error_type: str = "GeneralError"
    
    def __str__(self) -> str:
        return f"Error: {self.content}"


@dataclass
class CmdOutputObservation(Observation):
    """Observation from command execution."""
    
    command: str = ""
    exit_code: int = 0
    
    def __str__(self) -> str:
        return f"Command: {self.command}\nExit Code: {self.exit_code}\nOutput:\n{self.content}"
