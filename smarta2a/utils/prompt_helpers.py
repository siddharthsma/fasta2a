# Library imports
from typing import Optional, List

# Local imports
from smarta2a.client.tools_manager import ToolsManager
from smarta2a.utils.types import AgentCard

def build_system_prompt(
    base_prompt: Optional[str],
    tools_manager: ToolsManager,
    mcp_server_urls_or_paths: Optional[List[str]] = None,
    agent_cards: Optional[List[AgentCard]] = None
) -> str:
    """
    Compose the final system prompt by combining the base prompt
    with a clear listing of available tools.
    """
    header = base_prompt or "You are a helpful assistant with access to the following tools:"
    
    if mcp_server_urls_or_paths:
        mcp_tools_desc = tools_manager.describe_tools("mcp")
        header += f"\n\nAvailable tools:\n{mcp_tools_desc}"
    
    if agent_cards:
        a2a_tools_desc = tools_manager.describe_tools("a2a")
        header += f"\n\nIf needed, you can delegate parts of your task to other agents. The Agents you can use are:\n{_print_agent_list(agent_cards)}\n\nUse the following tools to send tasks to an agent:\n{a2a_tools_desc}"
    
    return header 


def _print_agent_list(agents: List[AgentCard]) -> None:
    """Prints multiple agents with separators"""
    separator = "---"
    agent_strings = [agent.pretty_print(include_separators=False) for agent in agents]
    full_output = [separator]
    full_output.extend(agent_strings)
    full_output.append(separator)
    print("\n".join(full_output))