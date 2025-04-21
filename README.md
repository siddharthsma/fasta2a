# SmartA2A

A Python package for creating a server following Google's Agent2Agent protocol

## Features

✅ **Full A2A Protocol Compliance** - Implements all required endpoints and response formats

⚡ **Decorator-Driven Development** - Rapid endpoint configuration with type safety

🧩 **Automatic Protocol Conversion** - Simple returns become valid A2A responses 

🔀 **Flexible Response Handling** - Support for Tasks, Artifacts, Streaming, and raw protocol types if needed!

🛡️ **Built-in Validation** - Automatic Pydantic validation of A2A schemas  

⚡ **Single File Setup** - Get compliant in <10 lines of code

🌍 **Production Ready** - CORS, async support, and error handling included

## Installation

```bash
pip install smarta2a
```

## Simple Echo Server Implementation

```python
from smarta2a.server import SmartA2A

app = SmartA2A("EchoServer")

@app.on_send_task()
def handle_task(request):
    """Echo the input text back as a completed task"""
    input_text = request.content[0].text
    return f"Echo: {input_text}"

if __name__ == "__main__":
    app.run()
```

Automatically contructs the response:

```json
{
  "jsonrpc": "2.0",
  "id": "test",
  "result": {
    "id": "echo-task",
    "status": {"state": "completed"},
    "artifacts": [{
      "parts": [{"type": "text", "text": "Echo: Hello!"}]
    }]
  }
}
```

## Development

To set up the development environment:

```bash
# Clone the repository
git clone https://github.com/siddharthsma/smarta2a.git
cd smarta2a

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 