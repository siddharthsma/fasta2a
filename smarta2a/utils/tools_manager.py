# Library imports
import json
from typing import List, Dict, Any

# Local imports
from smarta2a.client.smart_mcp_client import SmartMCPClient

class ToolsManager:
    """
    Manages loading, describing, and invoking tools from various providers.
    """
    def __init__(self):
        self.tools_list: List[Any] = []
        self.clients: Dict[str, Any] = {}

    def load_mcp_tools(self, urls_or_paths: List[str]) -> None:
        for url in urls_or_paths:
            client = SmartMCPClient(url)
            for tool in client.list_tools():
                self.tools_list.append(tool)
                self.clients[tool.name] = client

    def register_tools(self, tools: List[Any], client: Any = None) -> None:
        """Register arbitrary tools with an optional client for invocation."""
        for tool in tools:
            self.tools_list.append(tool)
            if client:
                self.clients[tool.name] = client

    def get_tools(self) -> List[Any]:
        return self.tools_list

    def describe_tools(self) -> str:
        lines = []
        for tool in self.tools_list:
            schema = json.dumps(tool.input_schema, indent=2)
            lines.append(
                f"- **{tool.name}**: {tool.description}\n  Parameters schema:\n  ```json\n{schema}\n```"
            )
        return "\n".join(lines)

    def get_client(self, tool_name: str) -> Any:
        return self.clients.get(tool_name)

    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        client = self.get_client(tool_name)
        if not client:
            raise ValueError(f"Tool not found: {tool_name}")
        return await client.call_tool(tool_name, args)