import asyncio
import base64
from playwright.async_api import Page
from agents import Agent, Runner
from types import SimpleNamespace   # NEW IMPORT

# Custom InputDict to support to_input_item()
class InputDict(dict):
    def to_input_item(self):
        return self

async def select_item_agent(page: Page):
    tools_defs = [
        {
            "type": "function",
            "name": "back",
            "description": "Go back to the previous page.",
            "parameters": {},
        },
        {
            "type": "function",
            "name": "goto",
            "description": "Go to a specific URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Fully qualified URL to navigate to.",
                    },
                },
                "additionalProperties": False,
                "required": ["url"],
            },
        },
        {
            "type": "function",
            "name": "click",
            "description": "Click on a specific element on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector of the element to click.",
                    },
                },
                "additionalProperties": False,
                "required": ["selector"],
            },
        },
    ]
    # Use the dictionary definitions directly.
    tools = tools_defs
    agent = Agent(
        name="Amazon Mango Selector",
        instructions=(
            "You are an agent that helps select the first mango item on an Amazon search results page. "
            "Identify the correct item and respond with a JSON object containing a 'click' action with the CSS selector to click."
        ),
        tools=tools
    )
    page_content = await page.content()
    screenshot_bytes = await page.screenshot()
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    input_data = [InputDict({
        "page_content": page_content,
        "screenshot": f"data:image/png;base64,{screenshot_base64}",
        "message": "Select the first mango item on the page.",
    })]
    result = await Runner.run(agent, input_data)
    return result