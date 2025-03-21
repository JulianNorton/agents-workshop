import asyncio
import base64
from playwright.async_api import Page
from agents import Agent, Runner

# Custom InputDict to support to_input_item()
class InputDict(dict):
    def to_input_item(self):
        return self

async def mango_finder_agent(page: Page):
    tool_defs = [
        {
            "type": "function",
            "name": "fill",
            "description": "Fill an input element with given text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the input element."},
                    "text": {"type": "string", "description": "Text to input."}
                },
                "additionalProperties": False,
                "required": ["selector", "text"]
            }
        },
        {
            "type": "function",
            "name": "click_submit",
            "description": "Click the search submit button to submit the query. Since the agent only sees an image, it should identify a clear submit button.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the submit button."}
                },
                "additionalProperties": False,
                "required": ["selector"]
            }
        }
    ]
    # Use plain dictionaries directly
    tools = tool_defs
    agent = Agent(
        name="Mango Finder",
        instructions=(
            "You are an agent that helps perform a dynamic search for mango slices. "
            "Identify the search input field on the page and respond with actions to fill it with 'mango slices', "
            "then identify and click the submit button to run the search."
        ),
        tools=tools
    )
    page_content = await page.content()
    screenshot_bytes = await page.screenshot()
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    input_data = [InputDict({
        "page_content": page_content,
        "screenshot": f"data:image/png;base64,{screenshot_base64}",
        "message": "Perform a search for mango slices."
    })]
    result = await Runner.run(agent, input_data)
    return result