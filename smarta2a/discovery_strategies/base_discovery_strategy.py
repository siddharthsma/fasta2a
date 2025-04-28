# Library imports
from abc import ABC, abstractmethod
from typing import List


class BaseDiscoveryStrategy(ABC):
    """
    Base class for discovery strategies.
    """
    @abstractmethod
    def get_tools(self) -> List[str]:
        pass
