# Library imports
from typing import Optional, Dict, Any, List
import base64

# Local imports
from smarta2a.state_stores.base_state_store import BaseStateStore
from smarta2a.file_stores.base_file_store import BaseFileStore
from smarta2a.history_update_strategies.history_update_strategy import HistoryUpdateStrategy
from smarta2a.utils.types import Message, StateData, Task, TaskStatus, TaskState, PushNotificationConfig, Part, FilePart
from smarta2a.server.nats_client import NATSClient

class StateManager:
    def __init__(self, state_store: BaseStateStore, file_store: BaseFileStore, history_strategy: HistoryUpdateStrategy, nats_server_url: Optional[str] = "nats://localhost:4222", push_notification_config: Optional[PushNotificationConfig] = None):
        self.state_store = state_store
        self.file_store = file_store
        self.strategy = history_strategy
        self.nats_client = NATSClient(server_url=nats_server_url)
        self.push_notification_config = push_notification_config
    
    async def load(self):
        await self.nats_client.connect()
    

    async def unload(self):
        await self.nats_client.close()
    
    def _initialize_empty_state(
        self,
        task_id: str,
        session_id: str,
        push_notification_config: Optional[PushNotificationConfig] = None
    ) -> StateData:
        """
        Build a fresh StateData and persist it.
        """
        initial_task = Task(
            id=task_id,
            sessionId=session_id,
            status=TaskStatus(state=TaskState.WORKING),
            artifacts=[],
            history=[],
            metadata={}
        )

        # Use self.push_notification_config if push_notification_config is None
        notification_config = push_notification_config if push_notification_config is not None else self.push_notification_config

        state = StateData(
            task_id=task_id,
            task=initial_task,
            context_history=[],
            push_notification_config=notification_config
        )
        self.state_store.initialize_state(state)
        return state

    async def get_or_create_and_update_state(
        self,
        task_id: str,
        session_id: str,
        message: Message,
        metadata: Optional[Dict[str, Any]] = None,
        push_notification_config: Optional[PushNotificationConfig] = None
    ) -> StateData:
        """
        Fetch existing StateData, or initialize & persist a new one.
        """
        existing_state = self.state_store.get_state(task_id)
        if not existing_state:
            latest_state = self._initialize_empty_state(
                task_id, session_id, push_notification_config
            )
        else:
            latest_state = existing_state.copy()

        latest_state.task.history.append(message)
        latest_state.context_history = self.strategy.update_history(
            existing_history=latest_state.context_history,
            new_messages=[message]
        )
        latest_state.task.metadata = metadata

        # Process files before persistence
        await self._process_file_parts(latest_state)

        await self.update_state(latest_state)

        return latest_state
    
    async def get_and_update_state_from_webhook(self, task_id: str, result: Task) -> StateData:
        """
        Update existing state with webhook result data, including:
        - Merges task history from result
        - Extracts messages from artifacts' parts
        - Updates context history using strategy
        - Merges artifacts and metadata
        
        Raises ValueError if no existing state is found
        """
        existing_state = self.state_store.get_state(task_id)
        if not existing_state:
            raise ValueError(f"No existing state found for task_id: {task_id}")

        updated_state = existing_state.copy()
        new_messages = []

        # Add messages from result's history
        if result.history:
            new_messages.extend(result.history)

        # Extract messages from result's artifacts
        for artifact in result.artifacts or []:
            if artifact.parts:
                artifact_message = Message(
                    role="tool",
                    parts=artifact.parts,
                    metadata=artifact.metadata
                )
                new_messages.append(artifact_message)

        # Update task history (merge with existing)
        if new_messages:
            if updated_state.task.history is None:
                updated_state.task.history = []
            updated_state.task.history.extend(new_messages)

        # Update context history using strategy
        updated_state.context_history = self.strategy.update_history(
            existing_history=updated_state.context_history,
            new_messages=new_messages
        )

        # Merge artifacts
        if result.artifacts:
            if updated_state.task.artifacts is None:
                updated_state.task.artifacts = []
            updated_state.task.artifacts.extend(result.artifacts)

        # Merge metadata
        if result.metadata:
            updated_state.task.metadata = {
                **(updated_state.task.metadata or {}),
                **(result.metadata or {})
            }

        # Update task status if provided
        if result.status:
            updated_state.task.status = result.status
        
         # Process files before persistence
        await self._process_file_parts(updated_state)

        await self.update_state(updated_state)

        return updated_state
    
    def get_state(self, task_id: str) -> Optional[StateData]:
        return self.state_store.get_state(task_id)

    async def update_state(self, state_data: StateData):
        self.state_store.update_state(state_data.task_id, state_data)

        # Publish update through NATS client
        payload = self._prepare_update_payload(state_data)
        await self.nats_client.publish("state.updates", payload)
    
    def get_store(self) -> Optional[BaseStateStore]:
        return self.state_store
    
    def get_history_strategy(self) -> HistoryUpdateStrategy:
        return self.strategy
    
    # Private methods

    def _serialize_part(self, part: Part) -> dict:
        """Serialize a Part to frontend-compatible format"""
        part_data = part.model_dump()
        if part.type == "file" and part.file:
            if not part.file.bytes and not part.file.uri:
                raise ValueError("FilePart must have either bytes or uri")
        return part_data

    def _prepare_update_payload(self, state: StateData) -> Dict[str, Any]:
        """Prepare NATS message payload from state data"""
        return {
            "taskId": state.task_id,
            "taskName": state.task.metadata.get("taskName", ""),
            "parts": self._extract_artifact_parts(state.task),
            "complete": state.task.status.state == TaskState.COMPLETED
        }

    def _extract_artifact_parts(self, task: Task) -> List[dict]:
        """Extract and serialize parts from all artifacts"""
        parts = []
        if task.artifacts:
            for artifact in task.artifacts:
                for part in artifact.parts:
                    try:
                        parts.append(self._serialize_part(part))
                    except ValueError as e:
                        print(f"Invalid part in artifact: {e}")
        return parts
    
    async def _process_file_parts(self, state: StateData):
        """Replace file bytes with URIs and persist files"""
        for msg in state.context_history:
            for part in msg.parts:
                if isinstance(part, FilePart) and part.file.bytes:
                    uri = await self.file_store.upload(
                        content=base64.b64decode(part.file.bytes),
                        task_id=state.task_id,
                        filename=part.file.name
                    )
                    part.file.uri = uri
                    part.file.bytes = None  # Remove from state
