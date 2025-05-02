from smarta2a.server import SmartA2A
from smarta2a.utils.types import A2AResponse, TaskStatus, TaskState, TextPart, FileContent, FilePart

app = SmartA2A("EchoServer")

@app.on_send_task()
def handle_task(request):
    """Echo the input text back as a completed task"""
    input_text = request.content[0].text
    #return f"Response to task: {input_text}"
    return A2AResponse(
        content=[TextPart(type="text", text="Response to task: " + input_text), FilePart(type="file", file=FileContent(name="test.txt", bytes="test"))],
        status="working"
    )

@app.on_send_subscribe_task()
async def handle_subscribe_task(request):
    """Subscribe to the task"""
    input_text = request.content[0].text
    yield f"First response to the task: {input_text}"
    yield f"Second response to the task: {input_text}"
    yield f"Third response to the task: {input_text}"

@app.task_get()
def handle_get_task(request):
    """Get the task"""
    return f"Task: {request.id}"

@app.task_cancel()
def handle_cancel_task(request):
    """Cancel the task"""
    return f"Task cancelled: {request.id}"




   
