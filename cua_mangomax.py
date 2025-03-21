import sys, os
venv_path = os.path.join(os.path.dirname(__file__), "venv", "Lib", "site-packages")
# if venv_path not in sys.path:
#     sys.path.insert(0, venv_path)
# print("sys.path:", sys.path)

import asyncio
import base64
from playwright.async_api import async_playwright
from imhuman import solve_captcha
from agents import Agent, Runner, function_tool, ModelSettings  # added ModelSettings

# Add a custom InputDict so that the input supports to_input_item()
class InputDict(dict):
    def to_input_item(self):
        return self

# For select_item_via_agent, update tool definitions:
@function_tool
def back():
    raise NotImplementedError("Tool 'back' not implemented.")

@function_tool
def goto(url: str):
    raise NotImplementedError("Tool 'goto' not implemented.")

@function_tool
def click():
    # No selector needed now.
    raise NotImplementedError("Tool 'click' not implemented.")

async def select_item_via_agent(page):
    tools = [back, goto, click]

    agent = Agent(
        name="Amazon Mango Selector",
        instructions=(
            "You are an agent that helps select the first mango item on an Amazon search results page. "
            "Respond with a JSON object that indicates a 'click' action (no selector needed) when the correct item is found."
        ),
        tools=tools,
    )

    # Get the current page content
    page_content = await page.content()
    screenshot_bytes = await page.screenshot()
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    # Simplified input: only "role" and "content"
    input_data = [{"role": "user", "content": "Select the first mango item on the page."}]

    # Run the agent via Runner.run instead of agent.run
    result = await Runner.run(agent, input_data)
    print(f"Agent Result: {result.final_output}")

    # Use getattr() to safely retrieve an action.
    action = getattr(result, "action", None)
    if action and action.get("type") == "click":
        print("Agent requested a click action.")
        # Removed CSS click interaction – agentic only.
    else:
        print("No click action found in agent's output; skipping action.")

# For mango_finder, update tool definitions:
@function_tool
async def search_query(query: str):
    raise NotImplementedError("Tool 'search_query' not implemented.")

async def mango_finder(page):
    tools = [search_query]  # Use the new search_query tool only.
    agent = Agent(
        name="Mango Finder",
        instructions=(
            "You are a tool-enabled agent. To perform a search for mango slices, "
            "you must call the tool 'search_query' with the query 'mango slices'. "
            "Return only a JSON object representing the tool call without any additional text."
        ),
        tools=tools,
        model_settings=ModelSettings(tool_choice="required")
    )
    page_content = await page.content()
    screenshot_bytes = await page.screenshot()
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    input_data = [{"role": "user", "content": "Perform a search for mango slices."}]
    
    try:
        print("Running Mango Finder agent with input:", input_data)
        result = await Runner.run(agent, input_data)
        print("Mango Finder agent completed successfully.")
    except Exception as e:
        print("Runner.run failed:", e)
        # If available, print conversation history for debugging.
        try:
            convo = result.to_input_list()
            print("Conversation history:", convo)
        except Exception as history_err:
            print("Failed to retrieve conversation history:", history_err)
        raise

    print(f"Mango Finder Agent Result: {result.final_output}")
    # Process tool actions exclusively.
    if hasattr(result, "actions"):
        actions = result.actions if isinstance(result.actions, list) else [result.action]
        for action in actions:
            if action.get("type") == "search_query":
                print(f"Agent requested search_query with query: {action.get('query')}")
                # Execute the search using Playwright.
                await page.fill("input#twotabsearchtextbox", action.get("query"))
                await page.press("input#twotabsearchtextbox", "Enter")
            else:
                print("Unknown action")
    else:
        print("No tool actions returned; agent output: ", result.final_output)
    await page.wait_for_selector("div.s-main-slot", timeout=15000)

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        # Navigate to Amazon
        await page.goto("https://www.amazon.com")
        
        # Use imhuman's solve_captcha to handle any CAPTCHA challenge
        await solve_captcha(page)
        
        # Mango search using agent instead of hardcoded fill and press
        await mango_finder(page)
        
        # Use the agent to decide which item to select
        await select_item_via_agent(page)
        
        await page.wait_for_selector("#add-to-cart-button", timeout=100000)
        await page.click("#add-to-cart-button")
        print("Item added to cart. Stopping.")
        await asyncio.sleep(2)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
