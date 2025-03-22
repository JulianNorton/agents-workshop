import sys, os
import asyncio
import base64
import json  # NEW IMPORT
from imhuman import solve_captcha
from agents import Agent, Runner, function_tool, ModelSettings
from playwright.async_api import async_playwright
from utils import create_response  # Assume you have a create_response() utility
from mango_finder_agent import mango_finder_agent  # new import
from select_item_agent import select_item_agent

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

# New supervisor function that decides which agent to call based on task context.
async def agentic_supervisor(page):
    conversation = []
    max_turns = 3
    turn = 0
    done = False
    while not done and turn < max_turns:
        # Step 1: Capture a full-page screenshot and excerpt from page content.
        screenshot_bytes = await page.screenshot(full_page=True)
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        page_content = await page.content()
        excerpt = page_content[:500]  # first 500 characters
        
        # Step 2: Build the supervisor system prompt.
        supervisor_prompt = (
            "You are a supervisor agent whose goal is to order mangos. "
            "Based on the provided screenshot (as a base64 image) and page excerpt, decide which agent to invoke next. "
            "Available agents are: Mango Finder (to search for mango products) and Select Item (to choose a specific mango item from search results). "
            "If ordering is complete, return {\"agent\": \"Order Complete\"}. "
            "Return a JSON object exactly in this format: {\"agent\": \"Mango Finder\"} or {\"agent\": \"Select Item\"} or {\"agent\": \"Order Complete\"}."
        )
        
        # Append the supervisor prompt and context to the conversation.
        conversation.append({
            "role": "user",
            "content": supervisor_prompt,
            "image": f"data:image/png;base64,{screenshot_base64}",
            "page_excerpt": excerpt
        })
        
        # Step 3: Get supervisor decision. (Using dummy create_response here.)
        supervisor_response = create_response(model="supervisor-model", input=conversation, tools=[])
        try:
            resp_json = json.loads(supervisor_response["output"][0]["content"])
            chosen_agent = resp_json.get("agent")
        except Exception as e:
            print("Supervisor decision error:", e)
            chosen_agent = None
        
        print("Supervisor decided to invoke agent:", chosen_agent)
        
        # Step 4: Invoke the chosen agent.
        if chosen_agent == "Mango Finder":
            await mango_finder_agent(page)
        elif chosen_agent == "Select Item":
            selection_result = await select_item_agent(page)
            print("Selection agent response:", selection_result.final_output)
        elif chosen_agent == "Order Complete":
            print("Ordering complete. Supervisor handing off.")
            done = True
            break
        else:
            print("No valid supervisor decision; defaulting to Mango Finder then Select Item.")
            await mango_finder_agent(page)
            selection_result = await select_item_agent(page)
            print("Selection agent response:", selection_result.final_output)
        
        # Add the result of this turn to the conversation.
        conversation.append({
            "role": "assistant",
            "content": f"Agent {chosen_agent if chosen_agent else 'default'} executed."
        })
        turn += 1
        
    return

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await agentic_supervisor(page)
        await asyncio.sleep(2)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
