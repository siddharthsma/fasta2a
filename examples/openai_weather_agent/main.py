# Imports
from dotenv import load_dotenv
import os
import uvicorn
from smarta2a.agent.a2a_agent import A2AAgent
from smarta2a.model_providers.openai_provider import OpenAIProvider
from smarta2a.utils.types import AgentCard, AgentCapabilities, AgentSkill
from smarta2a.state_stores.inmemory_state_store import InMemoryStateStore
from smarta2a.history_update_strategies.append_strategy import AppendStrategy
from smarta2a.server.state_manager import StateManager
from smarta2a.file_stores.local_file_store import LocalFileStore


# Load environment variables from the .env file
load_dotenv()

# Fetch the value using os.getenv
api_key = os.getenv("OPENAI_API_KEY")

weather_agent_card = AgentCard(
    name="weather_agent",
    description="A weather agent that can help with weather related queries",
    version="0.1.0",
    url="http://localhost:8000/rpc",
    capabilities=AgentCapabilities(),
    skills=[AgentSkill(id="weather_forecasting", name="Weather Forecasting", description="Can get weather forecast for a given latitude and longitude"),
            AgentSkill(id="weather_alerts", name="Weather Alerts", description="Can get weather alerts for a US state")]
)


openai_provider = OpenAIProvider(
    api_key=api_key,
    model="gpt-4o-mini",
    base_system_prompt="You are a cheerful assistant that specialises in helping with weather related queries",
    mcp_server_urls_or_paths=["npx -y supergateway --sse https://mcp.pipedream.net/77239217-f8a1-4239-99cd-a3a69598f2ea/openweather_api"],
)

state_manager = StateManager(state_store=InMemoryStateStore(), file_store=LocalFileStore(), history_strategy=AppendStrategy())

# Create the agent
agent = A2AAgent(
    name="openai_agent",
    model_provider=openai_provider,
    agent_card=weather_agent_card,
    state_manager=state_manager
)

# Entry point
if __name__ == "__main__":
    uvicorn.run(agent.get_app(), host="0.0.0.0", port=8000)
