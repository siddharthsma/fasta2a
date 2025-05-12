# TODO: Implement a human agent that can be used to interact with the A2A server

# Library imports
from fastapi import Query
from fastapi.responses import JSONResponse
from typing import Optional

# Local imports
from smarta2a.server import SmartA2A
from smarta2a.model_providers.base_llm_provider import BaseLLMProvider
from smarta2a.server.state_manager import StateManager
from smarta2a.utils.types import StateData, SendTaskRequest, AgentCard, WebhookRequest, WebhookResponse, TextPart, DataPart, FilePart
from smarta2a.client.a2a_client import A2AClient

class A2AHuman:
    def __init__(
            self,
            name: str,
            model_provider: BaseLLMProvider,
            agent_card: AgentCard = None,
            state_manager: StateManager = None,
        ):
        self.model_provider = model_provider
        self.state_manager = state_manager
        self.app = SmartA2A(
            name=name,
            agent_card=agent_card,
            state_manager=self.state_manager
        )
        self.__register_handlers()

    def __register_handlers(self):
        @self.app.on_event("startup")
        async def on_startup():
            await self.model_provider.load()
        
        @self.app.app.get("/tasks")
        async def get_tasks(fields: Optional[str] = Query(None)):
            state_store = self.state_mgr.get_store()
            tasks_data = state_store.get_all_tasks(fields)
            return JSONResponse(content=tasks_data)
        
        @self.app.on_send_task(forward_to_webhook=True)
        async def on_send_task(request: SendTaskRequest, state: StateData):
            return "Give me some time to respond"
        
        @self.app.webhook()
        async def on_webhook(request: WebhookRequest, state: StateData):
            pass

    def get_app(self):
        return self.app


    
    