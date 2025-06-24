"""Action definitions for the standalone LLM editor."""

from dataclasses import dataclass
from typing import Optional, Any, ClassVar
from enum import Enum


class ActionType(str, Enum):
    """Enumeration of action types."""
    EDIT = "edit"
    READ = "read"
    RUN = "run"
    FINISH = "finish"
    MESSAGE = "message"


class FileEditSource(str, Enum):
    """Source of file edit implementation."""
    OH_ACI = "oh_aci"  # openhands-aci
    LLM_BASED_EDIT = "llm_based_edit"


class FileReadSource(str, Enum):
    """Source of file read implementation."""
    OH_ACI = "oh_aci"  # openhands-aci
    STANDARD = "standard"


@dataclass
class Action:
    """Base class for all actions."""
    action: str = ""
    thought: str = ""
    runnable: ClassVar[bool] = True
    
    # Metadata
    tool_call_metadata: Optional[Any] = None
    response_id: Optional[str] = None


@dataclass
class FileEditAction(Action):
    """File editing action compatible with OHEditor."""
    
    path: str = ""
    
    # OH_ACI arguments (for openhands-aci compatibility)
    command: str = ""  # view, create, str_replace, insert, undo_edit
    file_text: Optional[str] = None
    old_str: Optional[str] = None
    new_str: Optional[str] = None
    insert_line: Optional[int] = None
    
    # LLM-based editing arguments
    content: str = ""
    start: int = 1
    end: int = -1
    
    # Source configuration
    impl_source: FileEditSource = FileEditSource.OH_ACI
    
    # Action metadata
    action: str = ActionType.EDIT
    runnable: ClassVar[bool] = True
    
    def __post_init__(self):
        """Validate action parameters after initialization."""
        if not self.path:
            raise ValueError("File path is required")
        
        if self.impl_source == FileEditSource.OH_ACI:
            if not self.command:
                raise ValueError("Command is required for OH_ACI mode")
        elif self.impl_source == FileEditSource.LLM_BASED_EDIT:
            if not self.content:
                raise ValueError("Content is required for LLM_BASED_EDIT mode")


@dataclass
class FileReadAction(Action):
    """File reading action."""
    
    path: str = ""
    view_range: Optional[list[int]] = None
    start: int = 1
    end: int = -1
    impl_source: FileReadSource = FileReadSource.OH_ACI
    
    action: str = ActionType.READ
    runnable: ClassVar[bool] = True
    
    def __post_init__(self):
        """Validate action parameters after initialization."""
        if not self.path:
            raise ValueError("File path is required")


@dataclass
class CmdRunAction(Action):
    """Command execution action."""
    
    command: str = ""
    is_input: bool = False
    timeout: Optional[float] = None
    
    action: str = ActionType.RUN
    runnable: ClassVar[bool] = True
    
    def __post_init__(self):
        """Validate action parameters after initialization."""
        if not self.command:
            raise ValueError("Command is required")


@dataclass
class AgentFinishAction(Action):
    """Agent finish action."""
    
    final_thought: str = ""
    task_completed: Optional[bool] = None
    
    action: str = ActionType.FINISH
    runnable: ClassVar[bool] = False


@dataclass
class MessageAction(Action):
    """Message action for text responses."""
    
    content: str = ""
    wait_for_response: bool = True
    
    action: str = ActionType.MESSAGE
    runnable: ClassVar[bool] = False
    
    def __post_init__(self):
        """Validate action parameters after initialization."""
        if not self.content:
            raise ValueError("Message content is required")
