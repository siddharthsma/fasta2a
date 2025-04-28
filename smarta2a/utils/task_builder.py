# Library imports
from uuid import uuid4
from datetime import datetime
from typing import Any, List, Optional, Dict, Union
from pydantic import ValidationError

# Local imports
from smarta2a.utils.types import (
    Task,
    TaskStatus,
    TaskState,
    Artifact,
    Part,
    TextPart,
    FilePart,
    DataPart,
    Message,
    A2AResponse,
)

class TaskBuilder:
    def __init__(
        self,
        default_status: TaskState = TaskState.COMPLETED,
    ):
        self.default_status = default_status

    def build(
        self,
        content: Any,
        task_id: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str,Any]] = None,
        history: Optional[List[Message]] = None,
    ) -> Task:
        """Universal task construction from various return types."""
        history = history or []
        metadata = metadata or {}

        # 1) If the handler already gave us a full Task, just fix IDs & history:
        if isinstance(content, Task):
            content.sessionId = content.sessionId or session_id
            content.history = history + (content.history or [])
            content.metadata = content.metadata or metadata
            return content

        # 2) If they returned an A2AResponse, extract status/content:
        if isinstance(content, A2AResponse):
            # prefer the sessionId inside the A2AResponse
            sid = content.sessionId or session_id
            # merge metadata from builder-call and from A2AResponse
            md = {**(metadata or {}), **(content.metadata or {})}
            status = (
                content.status
                if isinstance(content.status, TaskStatus)
                else TaskStatus(state=content.status)
            )
            artifacts = self._normalize_content(content.content)
            return Task(
                id=task_id,
                sessionId=sid,
                status=status,
                artifacts=artifacts,
                metadata=md,
                history=history,
            )

        # 3) If they returned a plain dict describing a Task:
        if isinstance(content, dict):
            try:
                return Task(
                    **content,
                    sessionId=session_id or content.get("sessionId"),
                    metadata=metadata or content.get("metadata", {}),
                    history=history,
                )
            except ValidationError:
                pass

        # 4) Fallback: treat whatever they returned as “artifact content”:
        artifacts = self._normalize_content(content)
        return Task(
            id=task_id,
            sessionId=session_id,
            status=TaskStatus(state=self.default_status),
            artifacts=artifacts,
            metadata=metadata,
            history=history,
        )

    def normalize_from_status(
        self, status: TaskState, task_id: str, metadata: Dict[str,Any]
    ) -> Task:
        """Build a Task when only a cancellation or status‐only event occurs."""
        return Task(
            id=task_id,
            sessionId="",
            status=TaskStatus(state=status, timestamp=datetime.now()),
            artifacts=[],
            metadata=metadata,
            history=[],
        )

    def _normalize_content(self, content: Any) -> List[Artifact]:
        """Turn any handler return value into a list of Artifact."""
        if isinstance(content, Artifact):
            return [content]

        if isinstance(content, list) and all(isinstance(a, Artifact) for a in content):
            return content

        if isinstance(content, list):
            return [Artifact(parts=self._parts_from_mixed(content))]

        if isinstance(content, str):
            return [Artifact(parts=[TextPart(text=content)])]

        if isinstance(content, dict):
            # raw artifact dict
            return [Artifact.model_validate(content)]

        # explicit `Part` subclasses
        if isinstance(content, (TextPart, FilePart, DataPart)):
            return [Artifact(parts=[content])]

        # “unknown” object: try Pydantic → dict → fallback to text
        try:
            return [Artifact.model_validate(content)]
        except ValidationError:
            return [Artifact(parts=[TextPart(text=str(content))])]

    def _parts_from_mixed(self, items: List[Any]) -> List[Part]:
        parts: List[Part] = []
        for item in items:
            if isinstance(item, Artifact):
                parts.extend(item.parts)
            else:
                parts.append(self._create_part(item))
        return parts

    def _create_part(self, item: Any) -> Part:
        from smarta2a.utils.types import Part as UnionPart
        # guard against Union alias
        if isinstance(item, (TextPart, FilePart, DataPart)):
            return item
        if isinstance(item, str):
            return TextPart(text=item)
        if isinstance(item, dict):
            try:
                return UnionPart.model_validate(item)
            except ValidationError:
                return TextPart(text=str(item))
        return TextPart(text=str(item))
