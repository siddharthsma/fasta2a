# Library imports
from typing import AsyncGenerator
from openai import AsyncOpenAI

# SmartA2A imports
from smarta2a.model_providers.base_llm_provider import BaseLLMProvider

class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def generate(self, messages: list, **kwargs) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content

    async def generate_stream(self, messages: list, **kwargs) -> AsyncGenerator[str, None]:
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            **kwargs
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content