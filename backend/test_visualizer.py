import asyncio
from retrieval.visualizer import VisualizerAgent

async def test():
    agent = VisualizerAgent()
    context = ["Sales in 2021 were 100, sales in 2022 were 200, sales in 2023 were 300, and sales in 2024 were 400."]
    answer = "The sales have been increasing steadily from 100 in 2021 to 400 in 2024."
    filename = await agent.run(context, answer)
    print(f"Generated chart filename: {filename}")

if __name__ == "__main__":
    asyncio.run(test())
