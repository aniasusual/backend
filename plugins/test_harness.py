import ollama
from typing import AsyncGenerator, Dict, Any
from plugins.base import BaseHarness

class TestHarness(BaseHarness):
    """
    A simple test harness that uses Ollama to respond and potentially writes a file.
    """
    
    async def process_prompt(self, user_prompt: str, context: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        registry = context.get('registry')
        
        yield {"type": "status", "content": "Thinking..."}
        
        try:
            client = ollama.AsyncClient()
            response = await client.chat(
                model='qwen2.5-coder:14b',
                messages=[
                    {
                        'role': 'system', 
                        'content': 'You are a helpful coding assistant. Keep it brief. Write a short python script based on user prompt.'
                    },
                    {'role': 'user', 'content': user_prompt}
                ],
                stream=True
            )
            
            full_response = ""
            async for chunk in response:
                content = chunk['message']['content']
                full_response += content
                yield {"type": "token", "content": content}
                
            if "```python" in full_response and registry:
                yield {"type": "status", "content": "Extracting code and writing to file..."}
                
                try:
                    code_block = full_response.split("```python")[1].split("```")[0].strip()
                    write_res = registry.write_file("test_output.py", code_block)
                    yield {"type": "status", "content": f"Tool result: {write_res}"}
                except Exception as ex:
                    yield {"type": "status", "content": f"Failed to extract/write code: {str(ex)}"}

            yield {"type": "status", "content": "Done"}
            
        except ollama.ResponseError as e:
            yield {"type": "status", "content": f"Ollama Error: {e.error}. Ensure Ollama is running and model 'qwen2.5-coder:14b' is pulled."}
        except Exception as e:
            yield {"type": "status", "content": f"Error: {str(e)}"}
