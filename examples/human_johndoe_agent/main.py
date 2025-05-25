# Imports
from dotenv import load_dotenv
import os
import uvicorn
import json
from smarta2a.agent.a2a_human import A2AHuman
from smarta2a.model_providers.openai_provider import OpenAIProvider
from smarta2a.utils.types import AgentCard, AgentCapabilities, AgentSkill
from smarta2a.state_stores.inmemory_state_store import InMemoryStateStore
from smarta2a.history_update_strategies.append_strategy import AppendStrategy
from smarta2a.server.state_manager import StateManager
from smarta2a.file_stores.local_file_store import LocalFileStore

# Load environment variables from the .env file
load_dotenv()

john_doe_agent_card = AgentCard(
    name="john_doe",
    description="A traveller who can recommend good places to visit in a city",
    version="0.1.0",
    url="http://localhost:8003/rpc",
    capabilities=AgentCapabilities(),
    skills=[AgentSkill(id="recommend_places", name="Recommend places", description="Recommend places to visit in a city")]
)

state_manager = StateManager(state_store=InMemoryStateStore(), file_store=LocalFileStore(), history_strategy=AppendStrategy())

# Create the agent
agent = A2AHuman(
    name="john_doe",
    agent_card=john_doe_agent_card,
    state_manager=state_manager
)

# Entry point
if __name__ == "__main__":
    uvicorn.run(agent.get_app(), host="0.0.0.0", port=8003)
