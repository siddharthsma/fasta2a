<picture>
  <img alt="SmartA2A Logo" src="documentation/smarta2a_docs/smarta2a_small_banner.png" width="100%">
</picture>

<div>
<br>
</div>

**SmartA2A** is a Python framework that helps you build servers and AI agents that communicate using the [A2A (Agent2Agent) protocol](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/). A2A defines a common language that enables agents to exchange information and collaborate effectively across systems.

SmartA2A abstracts the complexities of the protocol, so you can focus on what matters—your agent's logic and behavior. It supports two primary use cases:

### ✅ 1. Build A2A-Compliant Servers

Use SmartA2A to expose key A2A methods through a simple decorator-based API. This allows you to:

- Build compliant server endpoints quickly
- Integrate your own agent logic using any framework (e.g., LangGraph, Google ADK, or custom code)
- Stay fully aligned with the A2A spec without boilerplate

### 🤖 2. Create Full-Fledged Agents with Minimal Code

SmartA2A can also be used to create standalone agents that:

- Speak the A2A protocol out of the box
- Collaborate with other agents seamlessly
- Connect to any MCP server you choose
- Require only a few lines of setup

---

SmartA2A makes it easy to build interoperable, communication-ready AI systems—whether you're extending existing frameworks or starting from scratch.


## Installation

```bash
pip install -U smarta2a
```

## Simple Echo Server Implementation

Here's a simple example of an echo server that demonstrates the core features of SmartA2A:

```python
from smarta2a.server import SmartA2A
from smarta2a.utils.types import A2AResponse, TaskStatus, TaskState, TextPart, FileContent, FilePart
from smarta2a.state_stores.inmemory_state_store import InMemoryStateStore

# Initialize the server with an in-memory state store
state_store = InMemoryStateStore()
app = SmartA2A("EchoServer", state_store=state_store)

@app.on_send_task()
async def handle_task(request, state):
    """Echo the input text back as a completed task"""
    input_text = request.content[0].text
    return f"Response to task: {input_text}"

@app.on_send_subscribe_task()
async def handle_subscribe_task(request, state):
    """Subscribe to the task and stream multiple responses"""
    input_text = request.content[0].text
    yield f"First response to the task: {input_text}"
    yield f"Second response to the task: {input_text}"
    yield f"Third response to the task: {input_text}"

@app.task_get()
def handle_get_task(request):
    """Get the task status"""
    return f"Task: {request.id}"

@app.task_cancel()
def handle_cancel_task(request):
    """Cancel the task"""
    return f"Task cancelled: {request.id}"
```

This example shows:
- Setting up a basic A2A server with state management
- Handling synchronous task requests with text and file responses
- Implementing streaming responses for subscription tasks
- Basic task management (get and cancel operations)

To run the echo server:
```bash
uvicorn path.to.echo_server.main.py:app
```

## Weather Agent Example

Here's an example of a weather agent that uses OpenAI's GPT model to handle weather-related queries. Note that you will need to setup the weather MCP server as a pre-requisite as specified by the [MCP Quick-start server tutorial](https://modelcontextprotocol.io/quickstart/server)

```python
from dotenv import load_dotenv
import os
import uvicorn
from smarta2a.agent.a2a_agent import A2AAgent
from smarta2a.model_providers.openai_provider import OpenAIProvider

# Load environment variables from the .env file
load_dotenv()

# Initialize OpenAI provider with weather-specific configuration
openai_provider = OpenAIProvider(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o-mini",
    base_system_prompt="You are a cheerful assistant that specialises in helping with weather related queries",
    mcp_server_urls_or_paths=["/path/to/weather.py"],  # Path to your weather service
)

# Create and run the agent
agent = A2AAgent(
    name="openai_agent",
    model_provider=openai_provider,
)

if __name__ == "__main__":
    uvicorn.run(agent.get_app(), host="0.0.0.0", port=8000)
```

This example demonstrates:
- Setting up an AI agent with OpenAI integration
- Configuring a specialized system prompt for weather queries
- Connecting to external weather services via MCP
- Running the agent as a standalone server

To run the weather agent:
```bash
python path/to/weather_agent/main.py
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 