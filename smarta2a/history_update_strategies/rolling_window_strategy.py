# Library imports
from typing import List

# Local imports
from smarta2a.utils.types import Message

class RollingWindowStrategy:
    def __init__(self, window_size: int):
        if window_size < 1:
            raise ValueError("window_size must be at least 1")
        self.window_size = window_size

    """Default append behavior"""
    def update_history(self, existing_history: List[Message], new_messages: List[Message]) -> List[Message]:
        combined = existing_history + new_messages
        return combined[-self.window_size:]