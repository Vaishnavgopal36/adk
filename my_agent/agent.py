from google.adk.agents import Agent, BaseAgent

MODEL = "gemini-3.5-flash-lite"

# Four distinct tutoring approaches, plus one router: five agents total.
AGENT_CONFIGS = {
    "socratic_tutor": (
        "Teaches Python using the Socratic method.",
        """Teach Python by asking one guiding question at a time.
        Wait for the student's answer before explaining.""",
    ),
    "direct_tutor": (
        "Provides direct Python explanations.",
        "Answer Python questions directly and clearly.",
    ),
    "code_first_tutor": (
        "Teaches Python through code examples.",
        "Start every explanation with a small Python code example.",
    ),
    "debugging_tutor": (
        "Teaches Python debugging.",
        "Focus on identifying bugs and explaining how to diagnose them.",
    ),
}

# Create the four specialist tutors from the configurations.
experimental_agents: list[BaseAgent] = [
    Agent(
        model=MODEL,
        name=name,
        description=description,
        # Transfer ownership of the reply; route the next user turn via root.
        mode="chat",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        instruction=f"""
        You are {name}.

        Your teaching instructions:
        {instruction}

        Begin user-facing responses with:
        [Agent: {name}]

        Answer the user directly. Do not transfer after answering.
        For follow-up questions, use the relevant conversation history.
        """,
    )
    for name, (description, instruction) in AGENT_CONFIGS.items()
]

# Root agent: routes requests to the selected agent.
root_agent = Agent(
    model=MODEL,
    name="experiment_router",
    description="Routes requests to experimental Python tutors.",
    instruction="""
    You are the orchestrator for four Python tutors. Select exactly one
    tutor and call transfer_to_agent with its name. The selected specialist
    owns the user-facing answer. Do not explain, introduce, summarize, copy,
    or acknowledge the specialist's answer. Do not generate tutoring text.

    Explicit selection takes priority:
    - Accept @agent_name: question or @agent_name followed by a question.
    - Transfer to the exact requested tutor when the name is valid.
    - If the name is invalid, ask the user to choose from socratic_tutor,
      direct_tutor, code_first_tutor, debugging_tutor. Do not silently
      substitute another tutor.

    Without an explicit selection, choose automatically:
    - debugging_tutor: errors, tracebacks, broken code, or diagnosing bugs.
    - socratic_tutor: requests for hints, guided practice, or learning by
      answering questions rather than receiving the solution immediately.
    - code_first_tutor: requests for code examples, implementations, or
      demonstrations. Prefer debugging_tutor when fixing existing code.
    - direct_tutor: general explanations and all other Python questions.

    Do not ask the user to choose a tutor when no name is supplied.
    Use the current request and relevant follow-up context when routing.
    For a follow-up answer or request to continue, select the previous tutor,
    especially during Socratic practice, unless the user changes topic or
    teaching style. A new explicit selection always takes priority.
    Only speak directly to clarify an invalid explicit tutor name.
    """,
    sub_agents=experimental_agents,
)
