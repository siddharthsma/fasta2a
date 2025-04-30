# Library imports
from typing import Dict, Callable, Optional

# Local imports

class HandlerRegistry:
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._subscriptions: Dict[str, Callable] = {}
        self._registered: set = set()

    def register(self, method: str, func: Callable, subscription: bool = False):
        if method in self._registered:
            raise RuntimeError(f"Method '{method}' already registered")
        target = self._subscriptions if subscription else self._handlers
        target[method] = func
        self._registered.add(method)

    def get_handler(self, method: str) -> Optional[Callable]:
        return self._handlers.get(method)

    def get_subscription(self, method: str) -> Optional[Callable]:
        return self._subscriptions.get(method)