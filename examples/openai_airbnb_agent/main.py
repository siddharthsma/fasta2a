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


# Load environment variables from the .env file
load_dotenv()

# Fetch the value using os.getenv
api_key = os.getenv("OPENAI_API_KEY")

airbnb_agent_card = AgentCard(
    name="airbnb_agent",
    description="An airbnb agent that can help with airbnb related queries",
    version="0.1.0",
    url="http://localhost:8002/rpc",
    capabilities=AgentCapabilities(),
    skills=[AgentSkill(id="search_listings", name="Search listings", description="Search for Airbnb listings by location, dates, guests, and more"),
            AgentSkill(id="get_listing_details", name="Get listing details", description="Get detailed information about a specific Airbnb listing by listing id, dates, guests, and more")]
)

openai_provider = OpenAIProvider(
    api_key=api_key,
    model="gpt-4o-mini",
    base_system_prompt="You are a cheerful assistant that specialises in helping with airbnb related queries",
    mcp_server_urls_or_paths=["@openbnb/mcp-server-airbnb --ignore-robots-txt"]
)

state_manager = StateManager(state_store=InMemoryStateStore(), history_strategy=AppendStrategy())

# Create the agent
agent = A2AAgent(
    name="openai_agent",
    model_provider=openai_provider,
    agent_card=airbnb_agent_card,
    state_manager=state_manager
)

# Entry point
if __name__ == "__main__":
    uvicorn.run(agent.get_app(), host="0.0.0.0", port=8002)
