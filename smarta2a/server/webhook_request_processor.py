# Library imports
from typing import Callable, Any, Optional

# Local imports
from smarta2a.server.state_manager import StateManager
from smarta2a.utils.types import WebhookRequest, WebhookResponse, StateData, Message
from smarta2a.client.a2a_client import A2AClient

class WebhookRequestProcessor:
    def __init__(self, webhook_fn: Callable[[WebhookRequest], Any], state_manager: Optional[StateManager] = None):
        self.webhook_fn = webhook_fn
        self.state_manager = state_manager
        self.a2a_aclient = A2AClient()

    async def process_request(self, request: WebhookRequest) -> WebhookResponse:
        if self.state_manager:
            state_data = self.state_manager.get_and_update_state_from_webhook(request.id, request.result)
            return await self._webhook_handler(request, state_data)
        else:
            return await self._webhook_handler(request)


    async def _webhook_handler(self, request: WebhookRequest, state_data: Optional[StateData] = None) -> WebhookResponse:
        try:
            # --- Step 1: Process Incoming Task ---
            if request.result:
                incoming_task = request.result
                
                # Initialize state_data if missing
                if not state_data:
                    state_data = StateData(
                        task_id=incoming_task.id,
                        task=incoming_task.copy(update={"artifacts": incoming_task.artifacts}),
                        context_history=[],
                        push_notification_config=None
                    )

            # --- Step 2: Call Webhook Function ---
            webhook_response = await self.webhook_fn(request, state_data) if state_data else await self.webhook_fn(request)
            
            # --- Step 3: Process Webhook Response ---
            if webhook_response.result:
                updated_task = webhook_response.result
                existing_task = state_data.task
                
                # Overwrite artifacts from response
                existing_task.artifacts = updated_task.artifacts.copy() if updated_task.artifacts else []
                
                # Merge metadata
                existing_task.metadata = {**(existing_task.metadata or {}), **(updated_task.metadata or {})}
                
                # Build messages from updated artifacts
                updated_parts = [part for artifact in updated_task.artifacts for part in artifact.parts] if updated_task.artifacts else []
                updated_messages = [Message(role="agent", parts=updated_parts, metadata=updated_task.metadata)]
                
                # Update context history again
                if self.state_manager:
                    history_strategy = self.state_manager.get_history_strategy()
                    state_data.context_history = history_strategy.update_history(
                        existing_history=state_data.context_history,
                        new_messages=updated_messages
                    )
                    await self.state_manager.update_state(state_data)

            # --- Step 4: Push Notification ---
            push_url = state_data.push_notification_config.url if state_data and state_data.push_notification_config else None
            
            if push_url:
                try:
                    self.a2a_aclient.send_to_webhook(webhook_url=push_url, id=state_data.task_id, task=state_data.task)
                except Exception as e:
                    return WebhookResponse(
                        id=request.id,
                        error=f"Push notification failed: {str(e)}"
                    )

            # --- Step 5: Return Final Response ---
            return WebhookResponse(
                id=request.id,
                result=state_data.task if state_data else None
            )
        
        except Exception as e:
            return WebhookResponse(id=request.id, error=f"Internal error: {str(e)}")