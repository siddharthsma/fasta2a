# Imports
from dotenv import load_dotenv
import os
import uvicorn
import json
from smarta2a.agent.a2a_agent import A2AAgent
from smarta2a.model_providers.openai_provider import OpenAIProvider
from smarta2a.utils.types import AgentCard, AgentCapabilities, AgentSkill, PushNotificationConfig
from smarta2a.state_stores.inmemory_state_store import InMemoryStateStore
from smarta2a.file_stores.local_file_store import LocalFileStore
from smarta2a.history_update_strategies.append_strategy import AppendStrategy
from smarta2a.server.state_manager import StateManager


# Load environment variables from the .env file
load_dotenv()

# OpenAIProvider details
api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("MODEL", "gpt-4o-mini")
base_system_prompt = os.getenv("BASE_SYSTEM_PROMPT", "You are a cheerful assistant that specialises in helping with tasks and queries")
mcp_server_urls_or_paths = json.loads(os.getenv("MCP_SERVER_URLS", "[]"))
collaborating_agent_urls = json.loads(os.getenv("COLLABORATING_AGENT_URLS", "[]"))

# Agent details
agent_name = os.getenv("AGENT_NAME", "openai-agent")
agent_description = os.getenv("AGENT_DESCRIPTION", "A friendly agent that can help with tasks or queries")
agent_url = os.getenv("AGENT_URL", "http://openai-agent:8000/rpc")
agent_skills = [AgentSkill(**skill) for skill in json.loads(os.getenv("SKILLS_JSON", "[]"))]

# NATS settings
nats_server_url = os.getenv("NATS_SERVER_URL", "nats://openai-agent-nats:4222")

# Push notification settings
push_notification_url = os.getenv("PUSH_NOTIFICATION_URL", "http://openai-agent:8000/webhook")

agent_card = AgentCard(
    name=agent_name,
    description=agent_description,
    version="0.1.0",
    url=agent_url,
    capabilities=AgentCapabilities(),
    skills=agent_skills
)

openai_provider = OpenAIProvider(
    api_key=api_key,
    model=model,
    base_system_prompt=base_system_prompt,
    mcp_server_urls_or_paths=mcp_server_urls_or_paths,
    agent_base_urls=collaborating_agent_urls
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
agent = A2AAgent(
    name=agent_card.name,
    model_provider=openai_provider,
    agent_card=agent_card,
    state_manager=state_manager
)

# Entry point
if __name__ == "__main__":
    uvicorn.run(agent.get_app(), host="0.0.0.0", port=8000)
