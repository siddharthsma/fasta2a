# Library imports
import json
from typing import AsyncGenerator, List, Optional, Union
from openai import AsyncOpenAI

# Local imports
from smarta2a.common.types import Message, TextPart, FilePart, DataPart, Part
from smarta2a.model_providers.base_llm_provider import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o", system_prompt: Optional[str] = None):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.system_prompt = system_prompt
        self.supported_media_types = [
            "image/png", "image/jpeg", "image/gif", "image/webp"
        ]

    def _convert_part(self, part: Union[TextPart, FilePart, DataPart]) -> dict:
        """Convert a single part to OpenAI-compatible format"""
        if isinstance(part, TextPart):
            return {"type": "text", "text": part.text}
            
        elif isinstance(part, FilePart):
            if part.file.mimeType not in self.supported_media_types:
                raise ValueError(f"Unsupported media type: {part.file.mimeType}")
                
            if part.file.uri:
                return {
                    "type": "image_url",
                    "image_url": {"url": part.file.uri}
                }
            elif part.file.bytes:
                return {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{part.file.mimeType};base64,{part.file.bytes}"
                    }
                }
                
        elif isinstance(part, DataPart):
            return {
                "type": "text",
                "text": f"[Structured Data]\n{json.dumps(part.data, indent=2)}"
            }
            
        raise ValueError(f"Unsupported part type: {type(part)}")

    def _convert_messages(self, messages: List[Message]) -> List[dict]:
        """Convert messages to OpenAI format with system prompt"""
        openai_messages = []
        
        # Add system prompt if provided
        if self.system_prompt:
            openai_messages.append({
                "role": "system",
                "content": self.system_prompt
            })
        
        # Process user-provided messages
        for msg in messages:
            role = "assistant" if msg.role == "agent" else msg.role
            content = []
            
            for part in msg.parts:
                try:
                    converted = self._convert_part(part)
                    content.append(converted)
                except ValueError as e:
                    if isinstance(part, FilePart):
                        content.append({
                            "type": "text",
                            "text": f"<Unsupported file: {part.file.name or 'unnamed'}>"
                        })
                    else:
                        raise e
                        
            openai_messages.append({
                "role": role,
                "content": content
            })
            
        return openai_messages

    async def generate(self, messages: List[Message], **kwargs) -> str:
        converted_messages = self._convert_messages(messages)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=converted_messages,
            **kwargs
        )
        return response.choices[0].message.content

    async def generate_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        converted_messages = self._convert_messages(messages)
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=converted_messages,
            stream=True,
            **kwargs
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content