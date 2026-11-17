from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

root_agent = Agent(
    model=LiteLlm(model="groq/qwen/qwen3.8-27b"),
    name="root_agent",
    description="A helpful AI assistant.",
    instruction="Answer user questions clearly and concisely.",
)
