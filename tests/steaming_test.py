from calendar import c
import os
import asyncio
import httpx
import json
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")

async def stream_chat(message: str):
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model":"deepseek-v4-pro",
                "messages":[{"role":"user","content":message}],
                "stream":True,
            },
            timeout=30.0,
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue

                data_str = line[6:]

                if data_str == "[DONE]":
                    break
                
                chunk = json.loads(data_str)
                
                content = chunk["choices"][0]["delta"].get("content","")
                if content:
                    print(content,end = "",flush=True)

async def main():
    print("AI:",end="",flush=True)
    await stream_chat("用三句话说说你能干什么？")
    print()

asyncio.run(main())
