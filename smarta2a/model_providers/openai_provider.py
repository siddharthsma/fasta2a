# Library imports
import json
from typing import AsyncGenerator, List, Dict, Optional, Union, Any
from openai import AsyncOpenAI

# Local imports
from smarta2a.utils.types import Message, TextPart, FilePart, DataPart, Part, AgentCard
from smarta2a.model_providers.base_llm_provider import BaseLLMProvider
from smarta2a.client.tools_manager import ToolsManager
from smarta2a.utils.prompt_helpers import build_system_prompt

class OpenAIProvider(BaseLLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_system_prompt: Optional[str] = None,
        mcp_server_urls_or_paths: Optional[List[str]] = None,
        agent_cards: Optional[List[AgentCard]] = None,
        # enable_discovery: bool = False
    ):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.mcp_server_urls_or_paths = mcp_server_urls_or_paths
        self.agent_cards = agent_cards
        # Store the base system prompt; will be enriched by tool descriptions
        self.base_system_prompt = base_system_prompt
        self.supported_media_types = [
            "image/png", "image/jpeg", "image/gif", "image/webp"
        ]
        # Initialize ToolsManager 
        self.tools_manager = ToolsManager()
        
    
    async def load(self):
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
                    "name": tool.name,
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
        max_iterations = 10

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



    async def generate_stream(
        self, messages: List[Message], **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Stream response chunks, handling tool calls when complete.
        """
        # Prepare messages including dynamic system prompt
        converted_messages = self._convert_messages(messages)
        max_iterations = 10

        for _ in range(max_iterations):
            # Start streaming completion with function-call support
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=converted_messages,
                tools=self._format_openai_tools(),
                tool_choice="auto",
                stream=True,
                **kwargs
            )

            full_content = []
            tool_calls: List[Dict[str, Any]] = []

            # Collect streamed tokens and tool call deltas
            async for chunk in stream:
                delta = chunk.choices[0].delta
                # Yield text content immediately
                if hasattr(delta, 'content') and delta.content:
                    full_content.append(delta.content)
                    yield delta.content

                # Accumulate tool call metadata
                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    for d in delta.tool_calls:
                        idx = d.index
                        # Ensure sufficient list length
                        while len(tool_calls) <= idx:
                            tool_calls.append({"id": "", "function": {"name": "", "arguments": ""}})
                        # Assign fields if present
                        if d.id:
                            tool_calls[idx]["id"] = d.id
                        if d.function.name:
                            tool_calls[idx]["function"]["name"] = d.function.name
                        if d.function.arguments:
                            tool_calls[idx]["function"]["arguments"] += d.function.arguments

            # If no tool calls were invoked, stream is complete
            if not tool_calls:
                return

            # Append completed assistant message with tool calls
            converted_messages.append({
                "role": "assistant",
                "content": "".join(full_content),
                "tool_calls": [
                    {"id": tc["id"],
                     "type": "function",
                     "function": {"name": tc["function"]["name"],
                                   "arguments": tc["function"]["arguments"]}
                    }
                    for tc in tool_calls
                ]
            })

            # Execute each tool call and append responses
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                try:
                    result = await self.tools_manager.call_tool(name, args)
                    result_content = result.content
                except Exception as e:
                    result_content = f"Error executing {name}: {e}"

                converted_messages.append({
                    "role": "tool",
                    "content": result_content,
                    "tool_call_id": tc["id"]
                })
        # If iterations exhausted without final completion
        raise RuntimeError("Max tool iteration depth reached in generate_stream().")