from mcp.client import ClientSession, sse_client, stdio_client, StdioServerParameters
from typing import Optional, Dict, Any

class SmartMCPClient:
    def __init__(self, base_url: str):
        """
        Initialize with the server URL. Headers are provided per request, not globally.
        """
        self.base_url = base_url
        self.session = None
        self.exit_stack = AsyncExitStack()
        self._connect_to_server()

    async def list_tools(self, session_id: Optional[str] = None) -> Any:
        """
        List tools with optional session_id header.
        """
        async with Client(self.base_url, headers=self._build_headers(session_id)) as client:
            return await client.list_tools()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], session_id: Optional[str] = None) -> Any:
        """
        Call a tool with dynamic session_id.
        """
        async with Client(self.base_url, headers=self._build_headers(session_id)) as client:
            return await client.call_tool(tool_name, arguments)

    async def list_resources(self, session_id: Optional[str] = None) -> Any:
        """
        List resources with optional session_id.
        """
        async with Client(self.base_url, headers=self._build_headers(session_id)) as client:
            return await client.list_resources()

    async def read_resource(self, resource_uri: str, session_id: Optional[str] = None) -> Any:
        """
        Read a resource with dynamic session_id.
        """
        async with Client(self.base_url, headers=self._build_headers(session_id)) as client:
            return await client.read_resource(resource_uri)

    async def get_prompt(self, prompt_name: str, arguments: Dict[str, Any], session_id: Optional[str] = None) -> Any:
        """
        Fetch a prompt with optional session_id.
        """
        async with Client(self.base_url, headers=self._build_headers(session_id)) as client:
            return await client.get_prompt(prompt_name, arguments)

    async def ping(self, session_id: Optional[str] = None) -> Any:
        """
        Ping server with optional session_id.
        """
        async with Client(self.base_url, headers=self._build_headers(session_id)) as client:
            return await client.ping()

    def _build_headers(self, session_id: Optional[str]) -> Dict[str, str]:
        """
        Internal helper to build headers dynamically.
        """
        headers = {}
        if session_id:
            headers["x-session-id"] = session_id
        return headers
