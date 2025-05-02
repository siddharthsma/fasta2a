# Library imports


# Local imports
from smarta2a.server import SmartA2A
from smarta2a.model_providers.base_llm_provider import BaseLLMProvider
from smarta2a.history_update_strategies.history_update_strategy import HistoryUpdateStrategy
from smarta2a.history_update_strategies.append_strategy import AppendStrategy
from smarta2a.state_stores.base_state_store import BaseStateStore
from smarta2a.state_stores.inmemory_state_store import InMemoryStateStore
from smarta2a.utils.types import StateData, SendTaskRequest

class A2AAgent:
    def __init__(
            self,
            name: str,
            model_provider: BaseLLMProvider,
            history_update_strategy: HistoryUpdateStrategy = None,
            state_store: BaseStateStore = None,
        ):
        self.model_provider = model_provider
        self.history_update_strategy = history_update_strategy or AppendStrategy()
        self.state_store = state_store or InMemoryStateStore()
        self.app = SmartA2A(
            name=name,
            history_update_strategy=self.history_update_strategy,
            state_store=self.state_store
        )
        self.__register_handlers()

    def __register_handlers(self):
        @self.app.on_event("startup")
        async def on_startup():
            await self.model_provider.load()

        @self.app.on_send_task()
        async def on_send_task(request: SendTaskRequest, state: StateData):
            response = await self.model_provider.generate(state.history)
            return response
        
    def get_app(self):
        return self.app


    
    