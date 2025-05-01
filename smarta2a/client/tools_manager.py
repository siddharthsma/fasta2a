# Library imports
import json
from typing import List, Dict, Any, Union, Literal

# Local imports
from smarta2a.client.smart_mcp_client import SmartMCPClient
from smarta2a.client.a2a_client import A2AClient
from smarta2a.utils.types import AgentCard

class ToolsManager:
    """
    Manages loading, describing, and invoking tools from various providers.
    Acts as a wrapper around the MCP and A2A clients.
    """
    def __init__(self):
        self.tools_list: List[Any] = []
        self.clients: Dict[str, Union[SmartMCPClient, A2AClient]] = {}

    def load_mcp_tools(self, urls_or_paths: List[str]) -> None:
        for url in urls_or_paths:
            mcp_client = SmartMCPClient(url)
            for tool in mcp_client.list_tools():
                self.tools_list.append(tool)
                self.clients[tool.name] = mcp_client

    def load_a2a_tools(self, agent_cards: List[AgentCard]) -> None:
        for agent_card in agent_cards:
            a2a_client = A2AClient(agent_card)
            for tool in a2a_client.list_tools():
                self.tools_list.append(tool)
            self.clients[tool.name] = a2a_client

    def get_tools(self) -> List[Any]:
        return self.tools_list


    def describe_tools(self, client_type: Literal["mcp", "a2a"]) -> str:
        lines = []
        for tool in self.tools_list:
            if client_type == "mcp" and isinstance(tool, SmartMCPClient):
                schema = json.dumps(tool.input_schema, indent=2)
                lines.append(
                    f"- **{tool.name}**: {tool.description}\n  Parameters schema:\n  ```json\n{schema}\n```"
                )
            elif client_type == "a2a" and isinstance(tool, A2AClient):
                lines.append(
                    f"- **{tool.name}**: {tool.description} Parameters schema:\n  ```json\n{schema}\n```"
                )
        return "\n".join(lines)

    def get_client(self, tool_name: str) -> Any:
        return self.clients.get(tool_name)

    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        client = self.get_client(tool_name)
        if not client:
            raise ValueError(f"Tool not found: {tool_name}")
        return await client.call_tool(tool_name, args)