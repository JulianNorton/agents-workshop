import asyncio
import base64
import json
from typing import Optional, Dict, Any
from playwright.async_api import Page
from openai import OpenAI
from agents import Agent, Runner, function_tool

class InputDict(dict):
    def to_input_item(self):
        return self

async def mango_finder_agent(page: Page, search_method: str = "auto") -> Dict[str, Any]:
    """
    Agent responsible for navigating to Amazon and searching for mango slices.
    
    Args:
        page: Playwright page object
        search_method: Method to use for searching - "auto", "cua", or "manual"
        
    Returns:
        Dict with status and result information
    """
    print(f"Mango Finder Agent starting with search method: {search_method}")
    
    # Auto-detect the best method if not specified
    if search_method == "auto":
        # Check if we're already on Amazon
        if "amazon.com" in page.url:
            print("Already on Amazon, determining best search method...")
            # Check if we have the OpenAI API key available for CUA
            try:
                client = OpenAI()
                search_method = "cua"  # Default to CUA if OpenAI client works
            except Exception as e:
                print(f"OpenAI client error: {e}, falling back to manual search")
                search_method = "manual"
        else:
            # If not on Amazon, default to CUA which can handle navigation
            search_method = "cua"
    
    # Choose search method based on parameter
    if search_method == "cua":
        return await search_with_cua(page)
    else:
        return await search_manually(page)

async def search_with_cua(page: Page) -> Dict[str, Any]:
    """Use the Computer-Using Agent to search for mango slices on Amazon."""
    client = OpenAI()
    
    # Initialize the CUA loop
    print("Starting Mango Finder with CUA model...")
    
    # Take initial screenshot to start the CUA loop
    screenshot_bytes = await page.screenshot(full_page=True)
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    # Initial request to the model with correct content format
    try:
        response = client.responses.create(
            model="computer-use-preview",
            tools=[{
                "type": "computer_use_preview",
                "display_width": int(page.viewport_size["width"]),
                "display_height": int(page.viewport_size["height"]),
                "environment": "browser"
            }],
            input=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Go to Amazon.com and search for 'mango slices'. "
                                            "If you're already on Amazon, just search for mango slices. "
                                            "Wait for the search results to load."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"}}
                ]
            }],
            reasoning={
                "generate_summary": "concise",
            },
            truncation="auto"
        )
    except Exception as e:
        print(f"Error initializing CUA: {e}")
        print("Falling back to manual search...")
        return await search_manually(page)
    
    # Start the CUA loop
    completed = False
    max_iterations = 10
    iteration = 0
    
    while not completed and iteration < max_iterations:
        iteration += 1
        print(f"CUA Loop Iteration: {iteration}")
        
        # Process reasoning if available
        for item in response.output:
            if item.type == "reasoning":
                if hasattr(item, "summary") and item.summary:
                    for summary in item.summary:
                        if hasattr(summary, "text"):
                            print(f"Agent reasoning: {summary.text}")
        
        # Find computer call actions
        computer_calls = [item for item in response.output if item.type == "computer_call"]
        if not computer_calls:
            print("No computer actions found. Loop completed.")
            completed = True
            break
        
        # Process the computer call (assuming at most one per response)
        computer_call = computer_calls[0]
        action = computer_call.action
        call_id = computer_call.call_id
        
        # Handle safety checks if present
        pending_safety_checks = []
        if hasattr(computer_call, "pending_safety_checks") and computer_call.pending_safety_checks:
            print(f"Safety checks required: {computer_call.pending_safety_checks}")
            pending_safety_checks = computer_call.pending_safety_checks
            
        # Execute the action on the page
        try:
            print(f"Executing action: {action.type}")
            
            if action.type == "click":
                await page.mouse.click(action.x, action.y, button=action.button)
                
            elif action.type == "type":
                await page.keyboard.type(action.text)
                
            elif action.type == "keypress":
                for key in action.keys:
                    await page.keyboard.press(key)
                    
            elif action.type == "scroll":
                await page.mouse.move(action.x, action.y)
                await page.evaluate(f"window.scrollBy({action.scroll_x}, {action.scroll_y})")
                
            elif action.type == "wait":
                await asyncio.sleep(2)  # Default wait time
                
            else:
                print(f"Unknown action type: {action.type}")
                
            # Give the page a moment to update after the action
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"Error executing action: {e}")
            # Take error screenshot for debugging
            error_screenshot = await page.screenshot()
            error_path = f"error_screenshot_{iteration}.png"
            with open(error_path, "wb") as f:
                f.write(error_screenshot)
            print(f"Error screenshot saved to {error_path}")
            
            # If we've had errors for multiple iterations, fall back to manual search
            if iteration > 3:
                print("Multiple CUA errors, falling back to manual search...")
                return await search_manually(page)
        
        # Take a new screenshot after the action
        screenshot_bytes = await page.screenshot(full_page=True)
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        
        # Build the next input with correct output format
        next_input = [{
            "call_id": call_id,
            "type": "computer_call_output",
            "output": {
                "type": "computer_screenshot",
                "image_url": f"data:image/png;base64,{screenshot_base64}"
            }
        }]
        
        # Add safety check acknowledgments if needed
        if pending_safety_checks:
            next_input[0]["acknowledged_safety_checks"] = pending_safety_checks
            
        # Continue the CUA loop
        try:
            response = client.responses.create(
                model="computer-use-preview",
                previous_response_id=response.id,
                tools=[{
                    "type": "computer_use_preview",
                    "display_width": int(page.viewport_size["width"]),
                    "display_height": int(page.viewport_size["height"]),
                    "environment": "browser"
                }],
                input=next_input,
                truncation="auto"
            )
        except Exception as e:
            print(f"Error in CUA loop: {e}")
            print("Falling back to manual search...")
            return await search_manually(page)
        
        # Check if we're done (on Amazon search results page)
        current_url = page.url
        if "amazon.com" in current_url and ("s?k=mango+slices" in current_url or "mango" in current_url.lower()):
            print("Successfully navigated to Amazon mango slices search results!")
            completed = True
            break
            
    # Return the final state
    return {
        "url": page.url,
        "status": "complete" if "amazon.com" in page.url and "mango" in page.url.lower() else "incomplete",
        "iterations": iteration,
        "method": "cua"
    }

async def search_manually(page: Page) -> Dict[str, Any]:
    """
    Manual search fallback that uses direct playwright commands to search for mango slices.
    This is used when CUA is unavailable or fails.
    """
    print("Using manual search approach for mango slices...")
    
    try:
        # If we're not on Amazon already, navigate there
        if "amazon.com" not in page.url:
            print("Navigating to Amazon.com...")
            await page.goto("https://www.amazon.com")
            await page.wait_for_load_state("networkidle", timeout=30000)
        
        # Find and use the search box with multiple selector attempts
        search_success = False
        selectors = [
            "input#twotabsearchtextbox", 
            "input[type='text']", 
            "input[name='field-keywords']",
            ".nav-search-field input",
            "[aria-label='Search']"
        ]
        
        for selector in selectors:
            try:
                print(f"Trying selector: {selector}")
                search_box = await page.query_selector(selector)
                
                if search_box:
                    print(f"Found search box with selector: {selector}")
                    # Clear existing text if any
                    await search_box.click({clickCount: 3})  # Triple-click to select all text
                    await page.keyboard.press("Delete")
                    
                    # Type search query and submit
                    await search_box.type("mango slices", delay=50)
                    await page.keyboard.press("Enter")
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    
                    print("Search query submitted, waiting for results...")
                    # Allow extra time for search results to load
                    await asyncio.sleep(3)
                    
                    # Verify search was successful
                    current_url = page.url
                    if "s?k=mango+slices" in current_url or "mango" in current_url.lower():
                        print("Successfully searched for mango slices!")
                        search_success = True
                        break
            except Exception as e:
                print(f"Error with selector {selector}: {e}")
                continue
        
        # If no selector worked, try a more direct approach
        if not search_success:
            print("Direct selectors failed, trying alternative approach...")
            try:
                # Focus on the page and use keyboard shortcuts
                await page.keyboard.press("Tab")  # Try to focus on an interactive element
                await page.keyboard.press("/")    # Some sites use / as a shortcut to search
                await asyncio.sleep(1)
                
                # Type search text
                await page.keyboard.type("mango slices")
                await page.keyboard.press("Enter")
                await page.wait_for_load_state("networkidle", timeout=30000)
                
                # Check if search worked
                if "s?k=mango+slices" in page.url or "mango" in page.url.lower():
                    print("Alternative search approach succeeded!")
                    search_success = True
            except Exception as e:
                print(f"Alternative search approach failed: {e}")
        
        # Return the result
        return {
            "url": page.url,
            "status": "complete" if search_success else "incomplete",
            "method": "manual"
        }
        
    except Exception as e:
        print(f"Error in manual search: {e}")
        return {
            "url": page.url,
            "status": "error",
            "error": str(e),
            "method": "manual"
        }

# Legacy tools kept for compatibility but not used with CUA approach
@function_tool
async def click_at(x: float, y: float, button: str = "left") -> dict:
    return {"action_result": f"Clicked at ({x},{y}) with {button} button"}

@function_tool
async def navigate_to(url: str) -> dict:
    """Navigate to the specified URL."""
    return {"action_result": f"Navigating to {url}"}

@function_tool
async def type_text(text: str) -> dict:
    """Type the specified text at the current cursor position."""
    return {"action_result": f"Typing: {text}"}

@function_tool
async def press_key(key: str) -> dict:
    """Press a specific key like 'Enter' or 'Tab'."""
    return {"action_result": f"Pressed key: {key}"}

@function_tool
async def search_on_amazon(query: str) -> dict:
    """Search for the specified query on Amazon."""
    return {"action_result": f"Searching for '{query}' on Amazon"}

# Legacy model action handler kept for reference
async def handle_model_action(page: Page, action: dict):
    """Legacy function kept for reference but not used with CUA approach."""
    # ...existing code...