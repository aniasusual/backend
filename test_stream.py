import asyncio
import ollama

async def test():
    client = ollama.AsyncClient()
    messages = [{"role": "user", "content": "What is 2+2? Use a tool."}]
    tools = [{
        "type": "function",
        "function": {
            "name": "add",
            "description": "Add numbers",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"}
                }
            }
        }
    }]
    try:
        stream = await client.chat(model="qwen2.5-coder:7b", messages=messages, tools=tools, stream=True)
        async for chunk in stream:
            print(chunk.message)
    except Exception as e:
        print("Error:", e)

asyncio.run(test())
