# Imports
from dotenv import load_dotenv
import os
import uvicorn
import json
from smarta2a.agent.a2a_human import A2AHuman
from smarta2a.utils.types import AgentCard, AgentCapabilities, AgentSkill, PushNotificationConfig
from smarta2a.state_stores.inmemory_state_store import InMemoryStateStore
from smarta2a.file_stores.local_file_store import LocalFileStore
from smarta2a.history_update_strategies.append_strategy import AppendStrategy
from smarta2a.server.state_manager import StateManager


# Load environment variables from the .env file
load_dotenv()

# Agent details
agent_name = os.getenv("AGENT_NAME", "johndoe-agent")
agent_description = os.getenv("AGENT_DESCRIPTION", "A friendly human that can help with tasks or queries")
agent_url = os.getenv("AGENT_URL", "http://johndoe-agent:8000/rpc")
agent_skills = [AgentSkill(**skill) for skill in json.loads(os.getenv("SKILLS_JSON", "[]"))]

# NATS settings
nats_server_url = os.getenv("NATS_SERVER_URL", "nats://johndoe-agent-nats:4222")

# Push notification settings
push_notification_url = os.getenv("PUSH_NOTIFICATION_URL", "http://johndoe-agent:8000/webhook")

agent_card = AgentCard(
    name=agent_name,
    description=agent_description,
    version="0.1.0",
    url=agent_url,
    capabilities=AgentCapabilities(),
    skills=agent_skills
)


state_manager = StateManager(
    state_store=InMemoryStateStore(),
    file_store=LocalFileStore(),
    history_strategy=AppendStrategy(),
    nats_server_url=nats_server_url,
    push_notification_config=PushNotificationConfig(
        url=push_notification_url
    )
)

# Create the agent
agent = A2AHuman(
    name=agent_card.name,
    agent_card=agent_card,
    state_manager=state_manager
)

# Entry point
if __name__ == "__main__":
    uvicorn.run(agent.get_app(), host="0.0.0.0", port=8000)
