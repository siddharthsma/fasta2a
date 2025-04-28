# Library imports
from mcp.server.fastmcp import FastMCP, Context

class A2AMCPServer:
    def __init__(self):
        self.mcp = FastMCP("A2AMCPServer")
        self._register_handlers()

    def _register_handlers(self):

        @self.mcp.middleware
        async def extract_session_id(request, call_next):
            # Extract 'x-session-id' from headers
            session_id = request.headers.get("x-session-id")
            # Store it in the request state for later access
            request.state.session_id = session_id
            # Proceed with the request processing
            response = await call_next(request)
            return response
        
        @self.mcp.tool()
        def send_task(ctx: Context, url: str, message: str):
            session_id = ctx.request.state.session_id
            pass

        @self.mcp.tool()
        def get_task():
            pass

        @self.mcp.tool()
        def cancel_task():
            pass
        
        

    def start(self):
        pass
