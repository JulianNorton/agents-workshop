import asyncio
import base64
import json
from typing import Optional, Dict, Any
from playwright.async_api import Page, TimeoutError
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
    
    print("Starting Mango Finder with CUA model...")
    
    # Take initial screenshot to start the CUA loop
    screenshot_bytes = await page.screenshot(full_page=True)
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    # Initial request to the model with CORRECT format based on documentation
    try:
        response = client.responses.create(
            model="computer-use-preview",
            tools=[{
                "type": "computer_use_preview",
                "display_width": int(page.viewport_size["width"]),
                "display_height": int(page.viewport_size["height"]),
                "environment": "browser"
            }],
            input=[
                {
                    "role": "user",
                    "content": [{
                        "type": "text", 
                        "text": "Go to Amazon.com and search for 'mango slices'. If you're already on Amazon, just search for mango slices. Wait for the search results to load."
                    }]
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64", 
                        "media_type": "image/png", 
                        "data": screenshot_base64
                    }
                }
            ],
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
                "type": "image",
                "source": {
                    "type": "base64", 
                    "media_type": "image/png", 
                    "data": screenshot_base64
                }
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
        
        # Find and use the search box - improved approach
        search_success = False
        
        # More robust approach to finding and using the search box
        search_field_found = False
        
        # Method 1: Try common selectors with improved error handling
        for selector in [
            "input#twotabsearchtextbox", 
            "input[type='text']", 
            "input[name='field-keywords']",
            ".nav-search-field input",
            "[aria-label='Search']"
        ]:
            try:
                print(f"Trying selector: {selector}")
                
                # Check if element exists first
                element = await page.query_selector(selector)
                if not element:
                    print(f"Element not found with selector: {selector}")
                    continue
                
                # Element exists, now try to interact with it
                print(f"Found search box with selector: {selector}")
                
                # Click on the search field (properly)
                await element.click()
                
                # Select all existing text and delete it
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
                
                # Type the search query
                await page.keyboard.type("mango slices")
                await page.keyboard.press("Enter")
                
                # Wait for search results
                print("Search query submitted, waiting for results...")
                try:
                    # Wait for URL to change to indicate search
                    await page.wait_for_url("**/s?k=*mango*", timeout=10000)
                    search_success = True
                    search_field_found = True
                    print("Search completed successfully!")
                    break
                except TimeoutError:
                    print("Timeout waiting for search results URL. Will verify another way.")
                    # Even if URL didn't change as expected, check if page content did
                    if "mango slices" in await page.content():
                        search_success = True
                        search_field_found = True
                        print("Search appears successful based on page content!")
                        break
            except Exception as e:
                print(f"Error with selector {selector}: {str(e)}")
                continue
        
        # Method 2: If selectors failed, try clicking at common positions where search box might be
        if not search_field_found:
            print("Direct selectors failed, trying positional click approach...")
            try:
                # Try clicking near the top of the page where search boxes typically are
                for y_pos in [50, 75, 100]:
                    for x_pos in [300, 400, 500, 600]:
                        try:
                            # Click at position
                            await page.mouse.click(x_pos, y_pos)
                            await asyncio.sleep(0.5)
                            
                            # Type search query
                            await page.keyboard.press("Control+a")  # Select all existing text
                            await page.keyboard.press("Backspace") # Clear existing text
                            await page.keyboard.type("mango slices")
                            await page.keyboard.press("Enter")
                            
                            # Wait for a moment to see if page changes
                            await asyncio.sleep(2)
                            
                            # Check if search happened
                            if "mango" in page.url or "mango" in await page.content():
                                print(f"Position-based search successful at ({x_pos}, {y_pos})!")
                                search_success = True
                                break
                        except Exception as e:
                            print(f"Error with position ({x_pos}, {y_pos}): {str(e)}")
                            continue
                    
                    if search_success:
                        break
            except Exception as e:
                print(f"Error in positional search approach: {str(e)}")
        
        # Method 3: Try keyboard shortcuts that might focus the search bar
        if not search_success:
            print("Trying keyboard shortcut approach...")
            try:
                # Some sites use / to focus search
                await page.keyboard.press("/")
                await asyncio.sleep(1)
                
                # Type search text
                await page.keyboard.type("mango slices")
                await page.keyboard.press("Enter")
                
                # Wait a moment to see if page changes
                await asyncio.sleep(2)
                
                # Check if search happened
                if "mango" in page.url or "mango" in await page.content():
                    print("Keyboard shortcut search successful!")
                    search_success = True
            except Exception as e:
                print(f"Keyboard shortcut approach failed: {str(e)}")
        
        # Method 4: Last resort - try to inject JavaScript to perform the search
        if not search_success:
            print("Trying JavaScript injection as last resort...")
            try:
                # Use JavaScript to locate and interact with the search field
                search_script = """
                // Try to find the search input
                let searchInput = document.querySelector('input[type="text"]') || 
                                 document.querySelector('input[name="field-keywords"]') ||
                                 document.querySelector('#twotabsearchtextbox') ||
                                 Array.from(document.querySelectorAll('input')).find(el => 
                                    el.placeholder && el.placeholder.toLowerCase().includes('search'));
                
                if (searchInput) {
                    // Focus on the input
                    searchInput.focus();
                    // Clear existing value
                    searchInput.value = '';
                    // Set new value
                    searchInput.value = 'mango slices';
                    
                    // Try to submit the form if available
                    let form = searchInput.closest('form');
                    if (form) {
                        form.submit();
                        return true;
                    }
                    
                    // If no form, simulate Enter key
                    const enterEvent = new KeyboardEvent('keydown', {
                        bubbles: true, cancelable: true, keyCode: 13
                    });
                    searchInput.dispatchEvent(enterEvent);
                    return true;
                }
                
                return false;
                """
                
                search_success = await page.evaluate(search_script)
                if search_success:
                    print("JavaScript-based search successful!")
                    await asyncio.sleep(5)  # Give more time for JS redirect to complete
                else:
                    print("JavaScript could not find a search input")
            except Exception as e:
                print(f"JavaScript injection approach failed: {str(e)}")
        
        # Return the final result
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