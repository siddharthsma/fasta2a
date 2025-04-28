# Library imports
from typing import Protocol, List
from typing import List

# Local imports
from smarta2a.utils.types import Message

class HistoryUpdateStrategy(Protocol):
    def update_history(
        self,
        existing_history: List[Message],
        new_messages: List[Message]
    ) -> List[Message]:
        """Process history with new messages"""
        pass