import asyncio

from pydantic import BaseModel

from agents import Agent, Runner, trace

"""
This example demonstrates a deterministic flow, where each step is performed by an agent.
1. The first agent generates a story outline
2. We feed the outline into the second agent
3. The second agent checks if the outline is good quality and if it is a scifi story
4. If the outline is not good quality or not a scifi story, we stop here
5. If the outline is good quality and a scifi story, we feed the outline into the third agent
6. The third agent writes the story
"""

strategy_outline_agent = Agent(
    model="gpt-4o-2024-08-06",
    name="strategy_outline_agent",
    instructions="Generate a very short go-to-market strategy for a brand new startup based on the user's input.",
)


class OutlineCheckerOutput(BaseModel):
    good_quality: bool
    is_saas: bool


outline_checker_agent = Agent(
    name="outline_checker_agent",
    instructions="Read the strategy outline, and judge the quality. Also, determine if it is a applicable to software startups.",
    output_type=OutlineCheckerOutput,
)

strategy_creation_agent = Agent(
    name="strategy_creation_agent",
    instructions="Write a short go to market strategy based on the given outline.",
    output_type=str,
)


async def main():
    input_prompt = input("What kind of startup do you want to make? ")

    # Ensure the entire workflow is a single trace
    with trace("Deterministic story flow"):
        # 1. Generate an outline
        outline_result = await Runner.run(
            strategy_outline_agent,
            input_prompt,
        )
        print("Outline generated")

        # 2. Check the outline
        outline_checker_result = await Runner.run(
            outline_checker_agent,
            outline_result.final_output,
        )

        # 3. Add a gate to stop if the outline is not good quality or not a scifi story
        assert isinstance(outline_checker_result.final_output, OutlineCheckerOutput)
        if not outline_checker_result.final_output.good_quality:
            print("Strategy is not good quality, so we stop here.")
            exit(0)

        if not outline_checker_result.final_output.is_saas:
            print("Strategy is not a applicable to software startups, so we stop here.")
            exit(0)

        print("This is a good enough outline so we'll continue")

        # 4. Write the story
        story_result = await Runner.run(
            strategy_creation_agent,
            outline_result.final_output,
        )
        print(f"Story: {story_result.final_output}")


if __name__ == "__main__":
    asyncio.run(main())