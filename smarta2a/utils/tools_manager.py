# Library imports
import json
from typing import List, Dict, Any, Union, Literal, Optional

# Local imports
from smarta2a.client.mcp_client import MCPClient
from smarta2a.client.a2a_client import A2AClient
from smarta2a.utils.types import AgentCard, Tool

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
                # Generate key and ensure Tool type with key
                key = f"mcp---{tool.name}"
                validated_tool = Tool(
                    key=key,
                    **tool.model_dump()  # Pydantic 2.x syntax (use .dict() for Pydantic 1.x)
                )
                self.tools_list.append(validated_tool)
                self.clients[key] = mcp_client

    async def load_a2a_tools(self, agent_cards: List[AgentCard]) -> None:
        for agent_card in agent_cards:
            a2a_client = A2AClient(agent_card)
            tools_list = await a2a_client.list_tools()
            for tool_dict in tools_list:
                # Generate key from agent URL and tool name
                key = f"{agent_card.name}---{tool_dict['name']}"

                # Build new description
                components = []
                original_desc = tool_dict['description']
                if original_desc:
                    components.append(original_desc)
                if agent_card.description:
                    components.append(f"Agent Description: {agent_card.description}")
                
                # Collect skill descriptions
                skill_descriptions = []
                for skill in agent_card.skills:
                    if skill.description:
                        skill_descriptions.append(skill.description)
                if skill_descriptions:
                    components.append(f"Agent's skills: {', '.join(skill_descriptions)}")
            
                # Update tool_dict with new description
                tool_dict['description'] = ". ".join(components)
                
                validated_tool = Tool(
                    key=key,
                    **tool_dict
                )
                self.tools_list.append(validated_tool)
                self.clients[key] = a2a_client

    def get_tools(self) -> List[Any]:
        return self.tools_list


    def describe_tools(self, client_type: Literal["mcp", "a2a"]) -> str:
        lines = []
        for tool in self.tools_list:
            schema = json.dumps(tool.inputSchema, indent=2)  # Fix: use inputSchema
            if client_type == "mcp":
                lines.append(
                    f"- **{tool.key}**: {tool.description}\n  Parameters schema:\n  ```json\n{schema}\n```"
                )
            elif client_type == "a2a":
                lines.append(
                    f"- **{tool.key}**: {tool.description}\n  Parameters schema:\n  ```json\n{schema}\n```"
                )

        return "\n".join(lines)

    def get_client(self, tool_key: str) -> Any:
        return self.clients.get(tool_key)
    
    async def call_tool(self, tool_key: str, args: Dict[str, Any], override_args: Optional[Dict[str, Any]] = None) -> Any:
        try:
            client = self.get_client(tool_key)
            tool_name = self._get_tool_name(tool_key)
            new_args = self._replace_with_override_args(args, override_args)
            result = await client.call_tool(tool_name, new_args)
            
            return result

        except Exception as e:
            # This will catch ANY error in the body above
            raise
    
    def _get_tool_name(self, tool_key: str) -> str:
        return tool_key.split("---")[1]
    
    def _replace_with_override_args(self, args: Dict[str, Any], override_args: Optional[Dict[str, Any]] = None):
        new_args = args.copy()
        if override_args:
            new_args.update(override_args)
        return new_args