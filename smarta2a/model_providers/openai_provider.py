# Library imports
import json
import httpx
from typing import AsyncGenerator, List, Dict, Optional, Union, Any
from openai import AsyncOpenAI
from pydantic import HttpUrl, ValidationError

# Local imports
from smarta2a.utils.types import Message, TextPart, FilePart, DataPart, Part, AgentCard
from smarta2a.model_providers.base_llm_provider import BaseLLMProvider
from smarta2a.utils.tools_manager import ToolsManager
from smarta2a.utils.prompt_helpers import build_system_prompt
from smarta2a.utils.agent_discovery_manager import AgentDiscoveryManager

class OpenAIProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_system_prompt: Optional[str] = None,
        mcp_server_urls_or_paths: Optional[List[str]] = None,
        agent_cards: Optional[List[AgentCard]] = None,
        agent_base_urls: Optional[List[HttpUrl]] = None,
        discovery_endpoint: Optional[HttpUrl] = None,
        timeout: float = 5.0,
        retries: int = 2
    ):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.mcp_server_urls_or_paths = mcp_server_urls_or_paths
        # Store the base system prompt; will be enriched by tool descriptions
        self.base_system_prompt = base_system_prompt
        self.supported_media_types = [
            "image/png", "image/jpeg", "image/gif", "image/webp"
        ]

        # Initialize discovery manager
        self.agent_discovery = AgentDiscoveryManager(
            agent_cards=agent_cards,
            agent_base_urls=agent_base_urls,
            discovery_endpoint=discovery_endpoint,
            timeout=timeout,
            retries=retries
        )

        self.agent_cards: List[AgentCard] = []
        # Initialize ToolsManager 
        self.tools_manager = ToolsManager()
        
    
    async def load(self):
        """Async initialization of resources"""
        # Discover agents first
        self.agent_cards = await self.agent_discovery.discover_agents()

        if self.mcp_server_urls_or_paths:
            await self.tools_manager.load_mcp_tools(self.mcp_server_urls_or_paths)
        
        if self.agent_cards:
            await self.tools_manager.load_a2a_tools(self.agent_cards)
    

    def _build_system_prompt(self) -> str:
        """Get the system prompt with tool descriptions."""
        return build_system_prompt(
            self.base_system_prompt,
            self.tools_manager,
            self.mcp_server_urls_or_paths,
            self.agent_cards
        )
    
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
        
        # Add system prompt
        openai_messages.append({
            "role": "system",
            "content": self._build_system_prompt()
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
    

    def _format_openai_tools(self) -> List[dict]:
        """
        Convert internal tools metadata to OpenAI's function-call schema.
        """
        openai_tools = []
        for tool in self.tools_manager.get_tools():
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.key,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            })
        return openai_tools


    async def generate(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        """
        Generate a complete response, invoking tools as needed.
        """
        # Ensure messages are Message objects
        messages = [msg if isinstance(msg, Message) else Message(**msg) for msg in messages]
        converted_messages = self._convert_messages(messages)
        max_iterations = 30

        for iteration in range(max_iterations):
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=converted_messages,
                tools=self._format_openai_tools(),
                **kwargs
            )
            message = response.choices[0].message

            # Detect and extract the tool/function call
            if getattr(message, 'function_call', None):
                name = message.function_call.name
                args_raw = message.function_call.arguments
            elif getattr(message, 'tool_calls', None):
                tc = message.tool_calls[0]
                name = tc.function.name
                args_raw = tc.function.arguments
            else:
                return message.content
            print(message)
            # Append the assistant's intent
            converted_messages.append({
                "role": "assistant",
                "content": None,
                "function_call": {"name": name, "arguments": args_raw}
            })

            # Parse arguments safely
            try:
                args = json.loads(args_raw or '{}')
            except json.JSONDecodeError:
                args = {}

            # Call the tool manager with name and parsed args
            try:
                tool_result = await self.tools_manager.call_tool(name, args)
            except Exception as e:
                tool_result = {"content": f"Error calling {name}: {e}"}

            # Extract content
            if hasattr(tool_result, 'content'):
                result_content = tool_result.content
            elif isinstance(tool_result, dict) and 'content' in tool_result:
                result_content = tool_result['content']
            else:
                result_content = str(tool_result)

            # Append the function/tool's response
            converted_messages.append({
                "role": "function",
                "name": name,
                "content": result_content
            })

        raise RuntimeError("Max tool iteration depth reached in generate().")


    async def generate_stream(self, messages: List[Union[Message, Dict[str, Any]]], **kwargs) -> AsyncGenerator[str, None]:
        """
        Stream response chunks, invoking tools as needed.
        """
        # Normalize incoming messages to your Message model
        msgs = [
            msg if isinstance(msg, Message) else Message(**msg)
            for msg in messages
        ]
        # Convert to OpenAI schema, including any prior tool results
        converted_messages = self._convert_messages(msgs)
        max_iterations = 30

        for _ in range(max_iterations):
            # Kick off the streaming completion
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=converted_messages,
                tools=self._format_openai_tools(),
                tool_choice="auto",
                stream=True,
                **kwargs
            )

            full_content = ""
            tool_calls: List[Dict[str, Any]] = []

            # As chunks arrive, yield them and collect any tool_call deltas
            async for chunk in stream:
                delta = chunk.choices[0].delta

                # 1) Stream content immediately
                if hasattr(delta, "content") and delta.content:
                    yield delta.content
                    full_content += delta.content

                # 2) Buffer up any function/tool calls for after the stream
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for d in delta.tool_calls:
                        idx = d.index
                        # Ensure list is long enough
                        while len(tool_calls) <= idx:
                            tool_calls.append({
                                "id": "",
                                "function": {"name": "", "arguments": ""}
                            })
                        if d.id:
                            tool_calls[idx]["id"] = d.id
                        if d.function.name:
                            tool_calls[idx]["function"]["name"] = d.function.name
                        if d.function.arguments:
                            tool_calls[idx]["function"]["arguments"] += d.function.arguments

            # If the assistant didn't invoke any tools, we're done
            if not tool_calls:
                return

            # Otherwise, append the assistant's outgoing call and loop for tool execution
            converted_messages.append({
                "role": "assistant",
                "content": full_content,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        }
                    }
                    for tc in tool_calls
                ]
            })

            # Execute each tool in turn and append its result
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                try:
                    tool_res = await self.tools_manager.call_tool(name, args)
                    result_content = getattr(tool_res, "content", None) or (
                        tool_res.get("content") if isinstance(tool_res, dict) else str(tool_res)
                    )
                except Exception as e:
                    result_content = f"Error executing {name}: {e}"

                converted_messages.append({
                    "role": "tool",
                    "content": result_content,
                    "tool_call_id": tc["id"]
                })

        raise RuntimeError("Max tool iteration depth reached in generate_stream().")



    