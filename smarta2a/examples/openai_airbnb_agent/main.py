# Imports
from dotenv import load_dotenv
import os
import uvicorn
from smarta2a.agent.a2a_agent import A2AAgent
from smarta2a.model_providers.openai_provider import OpenAIProvider



# Load environment variables from the .env file
load_dotenv()

# Fetch the value using os.getenv
api_key = os.getenv("OPENAI_API_KEY")


openai_provider = OpenAIProvider(
    api_key=api_key,
    model="gpt-4o-mini",
    base_system_prompt="You are a cheerful assistant that specialises in helping with airbnb related queries",
    mcp_server_urls_or_paths=["/Users/apple/.npm/_npx/1629930a2e066932/node_modules/@openbnb/mcp-server-airbnb/dist/index.js"],
)

# Create the agent
agent = A2AAgent(
    name="openai_agent",
    model_provider=openai_provider,
)

# Entry point
if __name__ == "__main__":
    uvicorn.run(agent.get_app(), host="0.0.0.0", port=8002)
