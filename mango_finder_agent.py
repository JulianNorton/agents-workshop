import asyncio
import base64
from playwright.async_api import Page
from agents import Agent, Runner, function_tool

class InputDict(dict):
    def to_input_item(self):
        return self

@function_tool
async def click_at(x: float, y: float, button: str) -> dict:
    # Dummy tool: returns the click coordinates as confirmation.
    return {"action_result": f"Clicked at ({x},{y}) with {button} button"}

async def handle_model_action(page: Page, action: dict):
    """
    Execute the model action based solely on LLM output.
    Expected action format:
      {"type": "click", "x": <number>, "y": <number>, "button": "left"}
    """
    action_type = action.get("type")
    try:
        match action_type:
            case "click":
                x = action.get("x")
                y = action.get("y")
                button = action.get("button", "left")
                print(f"Action: click at ({x}, {y}) with button '{button}'")
                await page.mouse.click(x, y, button=button)
            case _:
                print(f"Unrecognized action: {action}")
    except Exception as e:
        print(f"Error handling action {action}: {e}")

async def mango_finder_agent(page: Page):
    tools = [click_at]
    agent = Agent(
        name="Mango Finder",
        instructions=(
            "You are a tool-enabled agent. To perform a click on the page, "
            "you must call the tool 'click_at' with the x and y coordinates "
            "where you want to click. Return only a single JSON object in the following format: "
            '{"type": "click", "x": 100, "y": 200, "button": "left"} and nothing else.'
        ),
        tools=tools
    )
    input_data = [{"role": "user", "content": "Perform a click action using the provided coordinates."}]
    result = await Runner.run(agent, input_data, max_turns=2)
    print(f"Mango Finder Agent Result: {result.final_output}")
    if hasattr(result, "actions") and result.actions:
        actions = result.actions if isinstance(result.actions, list) else [result.action]
        for action in actions:
            if action.get("type") == "click":
                print(f"Agent requested click at coordinates: x={action.get('x')}, y={action.get('y')}, button={action.get('button')}")
                await handle_model_action(page, action)
            else:
                print("Unknown action")
    else:
        # Fallback: default click coordinates if the agent didn't provide any tool call.
        default_action = {"type": "click", "x": 100, "y": 200, "button": "left"}
        print("No valid tool action returned; using default click coordinates:")
        print(f"Default action: {default_action}")
        await handle_model_action(page, default_action)