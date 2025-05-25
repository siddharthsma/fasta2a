# Imports
from dotenv import load_dotenv
import os
import uvicorn
from smarta2a.agent.a2a_agent import A2AAgent
from smarta2a.model_providers.openai_provider import OpenAIProvider
from smarta2a.utils.types import PushNotificationConfig
from smarta2a.state_stores.inmemory_state_store import InMemoryStateStore
from smarta2a.file_stores.local_file_store import LocalFileStore
from smarta2a.history_update_strategies.append_strategy import AppendStrategy
from smarta2a.server.state_manager import StateManager


# Load environment variables from the .env file
load_dotenv()

# Fetch the value using os.getenv
api_key = os.getenv("OPENAI_API_KEY")

weather_agent_url = "http://localhost:8000"
airbnb_agent_url = "http://localhost:8002"
john_doe_agent_url = "http://localhost:8003"

push_notification_url = "http://localhost:8001/webhook"

openai_provider = OpenAIProvider(
    api_key=api_key,
    model="gpt-4o-mini",
    agent_base_urls=[weather_agent_url, airbnb_agent_url, john_doe_agent_url],
    mcp_server_urls_or_paths=["uvx pymupdf4llm-mcp@latest stdio"]
)

state_manager = StateManager(
    state_store=InMemoryStateStore(),
    file_store=LocalFileStore(),
    history_strategy=AppendStrategy(),
    push_notification_config=PushNotificationConfig(
        url=push_notification_url
    )
)

# Create the agent
agent = A2AAgent(
    name="openai_agent",
    model_provider=openai_provider,
    state_manager=state_manager
)

# Entry point
if __name__ == "__main__":
    uvicorn.run(agent.get_app(), host="0.0.0.0", port=8001)
