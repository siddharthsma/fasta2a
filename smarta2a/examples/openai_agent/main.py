# Imports
from dotenv import load_dotenv
import os
import uvicorn
import asyncio
from smarta2a.agent.a2a_agent import A2AAgent
from smarta2a.model_providers.openai_provider import OpenAIProvider



# Load environment variables from the .env file
load_dotenv()

# Fetch the value using os.getenv
api_key = os.getenv("OPENAI_API_KEY")


openai_provider = OpenAIProvider(
    api_key=api_key,
    model="gpt-4o-mini",
    mcp_server_urls_or_paths=["/Users/apple/Desktop/Code/weather/weather.py"],
)

# Create the agent
agent = A2AAgent(
    name="openai_agent",
    model_provider=openai_provider,
)

# Entry point
if __name__ == "__main__":
    uvicorn.run(agent.get_app(), host="0.0.0.0", port=8000)
