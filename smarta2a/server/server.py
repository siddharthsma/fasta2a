# Library imports
from typing import Callable, Any, Optional
from fastapi import FastAPI, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import uvicorn
from fastapi.responses import StreamingResponse

# Local imports
from smarta2a.server.handler_registry import HandlerRegistry
from smarta2a.server.state_manager import StateManager
from smarta2a.utils.task_builder import TaskBuilder
from smarta2a.server.json_rpc_request_processor import JSONRPCRequestProcessor
from smarta2a.server.webhook_request_processor import WebhookRequestProcessor

from smarta2a.utils.types import (
    JSONRPCResponse,
    TaskState,
    JSONRPCError,
    JSONRPCRequest,
    SendTaskRequest,
    SendTaskStreamingRequest,
    GetTaskRequest,
    CancelTaskRequest,
    SetTaskPushNotificationRequest,
    GetTaskPushNotificationRequest,
    SetTaskPushNotificationRequest,
    GetTaskPushNotificationRequest,
    StateData,
    AgentCard,
    WebhookRequest,
    WebhookResponse
)

class SmartA2A:
    def __init__(self,
                name: str,
                agent_card: Optional[AgentCard] = None,
                state_manager: Optional[StateManager] = None,
                **fastapi_kwargs
                ):
        self.name = name
        self.registry = HandlerRegistry()
        self.agent_card = agent_card
        self.state_mgr = state_manager
        self.app = FastAPI(title=name, **fastapi_kwargs)
        self.router = APIRouter()
        self._setup_cors()
        self._setup_routes()
        self.server_config = {
            "host": "0.0.0.0",
            "port": 8000,
            "reload": False
        }
        self.task_builder = TaskBuilder(default_status=TaskState.COMPLETED)
        self.webhook_fn = None

    # Add this method to delegate ASGI calls
    async def __call__(self, scope, receive, send):
        return await self.app(scope, receive, send)
    
    def on_event(self, event_name: str):
        return self.app.on_event(event_name) 
    
    def configure(self, **kwargs):
        self.server_config.update(kwargs)

    def add_cors_middleware(self, **kwargs):
        self.app.add_middleware(
            CORSMiddleware,
            **{k: v for k, v in kwargs.items() if v is not None}
        )

    def run(self):
        uvicorn.run(
            self.app,
            host=self.server_config["host"],
            port=self.server_config["port"],
            reload=self.server_config["reload"]
        )

    def _setup_cors(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _setup_routes(self):
        @self.app.on_event("startup")
        async def on_startup():
            if self.state_mgr:
                await self.state_mgr.load()

        @self.app.post("/rpc")    
        async def handle_request(request: Request):
            try:
                data = await request.json()
                req = JSONRPCRequest.model_validate(data)
            except Exception as e:
                return JSONRPCResponse(id=None, error=JSONRPCError(code=-32700, message="Parse error", data=str(e))).model_dump()

            #response = await self.process_request(req)
            response = await JSONRPCRequestProcessor(self.registry, self.state_mgr).process_request(req)

            # <-- Accept both SSE‐style responses:
            if isinstance(response, (EventSourceResponse, StreamingResponse)):
                return response
            print(response)
            # <-- Everything else is a normal pydantic JSONRPCResponse
            return response.model_dump()
        
        # Add agent.json endpoint if card exists
        if self.agent_card is not None:
            @self.app.get("/.well-known/agent.json", response_model=AgentCard)
            async def get_agent_card():
                """Return the agent's service description"""
                return self.agent_card
        
        
        @self.app.post("/webhook")
        async def handle_webhook(request: Request):
            try:
                data = await request.json()
                print("--- In handle_webhook in server.py ---")
                print(data)
                print("--- end of handle_webhook in server.py ---")
                req = WebhookRequest.model_validate(data)
            except Exception as e:
                return WebhookResponse(accepted=False, error=str(e)).model_dump()
            
            response = await WebhookRequestProcessor(self.webhook_fn, self.state_mgr).process_request(req)

            return response.model_dump()
            
        
    '''
    Setup the decorators for the various A2A methods.
    '''
    def on_send_task(self,forward_to_webhook: bool = False):
        def decorator(fn: Callable[[SendTaskRequest, Optional[StateData]], Any]) -> Callable:
            fn.forward_to_webhook = forward_to_webhook
            self.registry.register("tasks/send", fn)
            return fn
        return decorator

    def on_send_subscribe_task(self,forward_to_webhook: bool = False):
        def decorator(fn: Callable[[SendTaskStreamingRequest, Optional[StateData]], Any]):
            fn.forward_to_webhook = forward_to_webhook
            self.registry.register("tasks/sendSubscribe", fn, subscription=True)
            return fn
        return decorator

    def task_get(self):
        def decorator(fn: Callable[[GetTaskRequest], Any]):
            self.registry.register("tasks/get", fn)
            return fn
        return decorator

    def task_cancel(self):
        def decorator(fn: Callable[[CancelTaskRequest], Any]):
            self.registry.register("tasks/cancel", fn)
            return fn
        return decorator

    def set_notification(self):
        def decorator(fn: Callable[[SetTaskPushNotificationRequest], Any]):
            self.registry.register("tasks/pushNotification/set", fn)
            return fn
        return decorator

    def get_notification(self):
        def decorator(fn: Callable[[GetTaskPushNotificationRequest], Any]):
            self.registry.register("tasks/pushNotification/get", fn)
            return fn
        return decorator
    
    '''
    This is outside of the A2A protocol spec. A callback allows a re-triggering of an existing task by a external service.
    If a state store is provided, the callback will use the push notification config to call another callback.
    This effectively allows backward communication.
    '''

    def webhook(self):
        def decorator(fn: Callable[[WebhookRequest], Any]):
            self.webhook_fn = fn
            return fn
        return decorator
    
    
