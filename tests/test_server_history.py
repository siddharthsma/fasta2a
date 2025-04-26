# Library imports
import pytest
from fastapi.testclient import TestClient

# Local imports
from smarta2a.server import SmartA2A

@pytest.fixture
def a2a_server():
    server = SmartA2A("test-server")
    return server

@pytest.fixture
def client(a2a_server):
    #return TestClient(a2a_server.app)
    # Create client with explicit async_test_client context manager
    with TestClient(a2a_server.app) as client:
        yield client

# Add async teardown for server
@pytest.fixture(autouse=True)
async def cleanup():
    yield
    # Force close all app connections
    import anyio
    anyio.run(anyio.sleep, 0)  # Flush pending tasks