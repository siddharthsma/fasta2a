# Library imports
import re
import shlex
from typing import Dict, Any
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client


class MCPClient:
    def __init__(self):
        self.session = None
        self.exit_stack = AsyncExitStack()

    @classmethod
    async def create(cls, server_path_or_url: str):
        client = cls()
        await client._connect_to_server(server_path_or_url)
        return client

    async def _connect_to_sse_server(self, server_url: str):
        """Connect to an SSE MCP server."""
        self._streams_context = sse_client(url=server_url)
        streams = await self._streams_context.__aenter__()

        self._session_context = ClientSession(*streams)
        self.session = await self._session_context.__aenter__()

        # Initialize
        await self.session.initialize()

    async def _connect_to_stdio_server(self, server_script_path: str):
        """Connect to a stdio MCP server."""
        is_python = False
        is_javascript = False
        command = None
        args = [server_script_path]
        
        # Determine if the server is a file path or npm package
        if server_script_path.startswith("@") or "/" not in server_script_path:
            # Assume it's an npm package
            is_javascript = True
            args = shlex.split(server_script_path)
            command = "npx"
        else:
            # It's a file path
            is_python = server_script_path.endswith(".py")
            is_javascript = server_script_path.endswith(".js")
            if not (is_python or is_javascript):
                raise ValueError("Server script must be a .py, .js file or npm package.")
        
            command = "python" if is_python else "node"
            
        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=None
        )
        print(server_params)

        # Start the server
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.writer = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.writer))

        await self.session.initialize()

    async def _connect_to_server(self, server_path_or_url: str):
        """Connect to an MCP server (either stdio or SSE)."""
        # Check if the input is a URL (for SSE server)
        url_pattern = re.compile(r'^https?://')
        
        if url_pattern.match(server_path_or_url):
            # It's a URL, connect to SSE server
            await self._connect_to_sse_server(server_path_or_url)
        else:
            # It's a script path, connect to stdio server
            await self._connect_to_stdio_server(server_path_or_url)
    
    async def list_tools(self):
        """List available tools."""
        response = await self.session.list_tools()
        return response.tools
    
    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]):
        """Call a tool."""
        response = await self.session.call_tool(tool_name, tool_args)
        return response.content

    async def cleanup(self):
        """Clean up resources."""
        await self.exit_stack.aclose()
        if hasattr(self, '_session_context') and self._session_context:
            await self._session_context.__aexit__(None, None, None)
        if hasattr(self, '_streams_context') and self._streams_context:
            await self._streams_context.__aexit__(None, None, None)