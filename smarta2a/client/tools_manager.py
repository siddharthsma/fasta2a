# Library imports
import json
from typing import List, Dict, Any, Union, Literal

# Local imports
from smarta2a.client.mcp_client import MCPClient
from smarta2a.client.a2a_client import A2AClient
from smarta2a.utils.types import AgentCard

class ToolsManager:
    """
    Manages loading, describing, and invoking tools from various providers.
    Acts as a wrapper around the MCP and A2A clients.
    """
    def __init__(self):
        self.tools_list: List[Any] = []
        self.clients: Dict[str, Union[MCPClient, A2AClient]] = {}

    async def load_mcp_tools(self, urls_or_paths: List[str]) -> None:
        for url in urls_or_paths:
            mcp_client = await MCPClient.create(url)
            tools = await mcp_client.list_tools()
            for tool in tools:
                self.tools_list.append(tool)
                self.clients[tool.name] = mcp_client

    async def load_a2a_tools(self, agent_cards: List[AgentCard]) -> None:
        for agent_card in agent_cards:
            a2a_client = A2AClient(agent_card)
            tools = await a2a_client.list_tools()
            for tool in tools:
                self.tools_list.append(tool)
                self.clients[tool.name] = a2a_client

    def get_tools(self) -> List[Any]:
        return self.tools_list


    def describe_tools(self, client_type: Literal["mcp", "a2a"]) -> str:
        lines = []
        for tool in self.tools_list:
            schema = json.dumps(tool.inputSchema, indent=2)  # Fix: use inputSchema
            if client_type == "mcp":
                lines.append(
                    f"- **{tool.name}**: {tool.description}\n  Parameters schema:\n  ```json\n{schema}\n```"
                )
            elif client_type == "a2a":
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