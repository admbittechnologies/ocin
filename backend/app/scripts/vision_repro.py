import asyncio, base64, os
from pathlib import Path
from pydantic_ai import Agent, BinaryContent

async def main():
    img = Path("/tmp/test_house.png").read_bytes()
    agent = Agent(
        model="anthropic:claude-sonnet-4-5",
        system_prompt="You are a helpful assistant.",
    )
    result = await agent.run([
        "What do you see in this image?",
        BinaryContent(data=img, media_type="image/png"),
    ])
    print("OUTPUT:", result.output)
    print("USAGE:", result.usage())

asyncio.run(main())
