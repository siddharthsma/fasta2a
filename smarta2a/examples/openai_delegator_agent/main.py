# Imports
from dotenv import load_dotenv
import os
import uvicorn
from smarta2a.agent.a2a_agent import A2AAgent
from smarta2a.model_providers.openai_provider import OpenAIProvider
from smarta2a.utils.types import AgentCard, AgentCapabilities, AgentSkill


# Load environment variables from the .env file
load_dotenv()

# Fetch the value using os.getenv
api_key = os.getenv("OPENAI_API_KEY")

weather_agent_card = AgentCard(
    name="weather_agent",
    description="A weather agent that can help with weather related queries",
    version="0.1.0",
    url="http://localhost:8000",
    capabilities=AgentCapabilities(),
    skills=[AgentSkill(id="weather_forecasting", name="Weather Forecasting", description="Can get weather forecast for a given latitude and longitude"),
            AgentSkill(id="weather_alerts", name="Weather Alerts", description="Can get weather alerts for a US state")]
)


openai_provider = OpenAIProvider(
    api_key=api_key,
    model="gpt-4o-mini",
    agent_cards=[weather_agent_card]
)

# Create the agent
agent = A2AAgent(
    name="openai_agent",
    model_provider=openai_provider,
)

# Entry point
if __name__ == "__main__":
    uvicorn.run(agent.get_app(), host="0.0.0.0", port=8080)
