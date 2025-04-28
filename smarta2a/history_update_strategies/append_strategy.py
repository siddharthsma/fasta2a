# Library imports
from typing import List

# Local imports
from smarta2a.utils.types import Message

class AppendStrategy:
    """Default append behavior"""
    def update_history(self, existing_history: List[Message], new_messages: List[Message]) -> List[Message]:
        return existing_history + new_messages