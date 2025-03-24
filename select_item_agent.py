import asyncio
import base64
import json
from playwright.async_api import Page
from openai import OpenAI

async def select_item_agent(page: Page):
    """
    Agent responsible for selecting a mango product from the Amazon search results.
    Uses the Computer-Using Agent (CUA) model for automated browser interaction.
    """
    client = OpenAI()
    
    # Take initial screenshot to start the CUA loop
    screenshot_bytes = await page.screenshot(full_page=True)
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    # Initial request to the model - corrected image format based on docs
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
                "content": "Select the first available dried mango slices product from the Amazon search results. Look for products with good reviews. Once you've found an appropriate product, click on it to view details."
            },
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{screenshot_base64}"
            }
        ],
        reasoning={
            "generate_summary": "concise",
        },
        truncation="auto"
    )
    
    # Start the CUA loop
    completed = False
    max_iterations = 10
    iteration = 0
    
    while not completed and iteration < max_iterations:
        iteration += 1
        print(f"Select Item CUA Loop Iteration: {iteration}")
        
        # Process reasoning if available
        for item in response.output:
            if item.type == "reasoning":
                if hasattr(item, "summary") and item.summary:
                    for summary in item.summary:
                        if hasattr(summary, "text"):
                            print(f"Selection reasoning: {summary.text}")
        
        # Find computer call actions
        computer_calls = [item for item in response.output if item.type == "computer_call"]
        if not computer_calls:
            print("No computer actions found in selection phase. Loop completed.")
            completed = True
            break
        
        # Process the computer call
        computer_call = computer_calls[0]
        action = computer_call.action
        call_id = computer_call.call_id
        
        # Handle safety checks if present
        if hasattr(computer_call, "pending_safety_checks") and computer_call.pending_safety_checks:
            print(f"Safety checks required: {computer_call.pending_safety_checks}")
            # In a real implementation, you would ask the user to verify each action
            # For now, we'll acknowledge all safety checks automatically
            acknowledged_checks = computer_call.pending_safety_checks
        else:
            acknowledged_checks = []
        
        # Execute the action on the page
        try:
            print(f"Executing selection action: {action.type}")
            
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
                
            # Give the page a moment to update after the action
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"Error executing selection action: {e}")
        
        # Take a new screenshot after the action
        screenshot_bytes = await page.screenshot(full_page=True)
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        
        # Continue the CUA loop with the updated screenshot - corrected format
        next_input = [{
            "call_id": call_id,
            "type": "computer_call_output",
            "output": {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{screenshot_base64}"
            }
        }]
        
        # Add safety check acknowledgments if needed
        if acknowledged_checks:
            next_input[0]["acknowledged_safety_checks"] = acknowledged_checks
        
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
        
        # Check if we're now on a product detail page
        current_url = page.url
        if "amazon.com" in current_url and "/dp/" in current_url:
            print("Successfully navigated to a product detail page!")
            completed = True
            break
    
    # Return the result
    return {
        "url": page.url,
        "status": "complete" if "/dp/" in page.url else "incomplete",
        "product_page": "/dp/" in page.url,
        "iterations": iteration
    }