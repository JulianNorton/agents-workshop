import sys, os
import asyncio
import base64
import json
import re
from typing import List, Dict, Tuple, Optional, Union
from playwright.async_api import Page
from agents import Agent, Runner
from openai import OpenAI

# This Agent is used as a fallback method for CAPTCHA solving
# It's only invoked in the get_multiple_captcha_solutions method which is UNUSED in the main flow
captcha_ocr_agent = Agent(
    name="CAPTCHA OCR Agent",
    instructions="You are an expert at solving CAPTCHAs. Examine the image and extract ONLY the CAPTCHA characters or text. Return ONLY the characters with no additional text or explanations.",
    model="gpt-4o"  # Using the most capable model for CAPTCHA solving
)

async def solve_captcha(page: Page) -> Dict:
    """
    Main CAPTCHA solver function that orchestrates the entire process:
    1. Takes a screenshot of the CAPTCHA
    2. Processes the image to extract the CAPTCHA text
    3. Locates the input field and submit button
    4. Enters the CAPTCHA text and submits
    5. Verifies if solution was successful
    
    Returns a dictionary with:
    - text: the CAPTCHA solution
    - success: whether the CAPTCHA was successfully solved
    - message: a user-friendly message about the result
    """
    # Wait for the page to fully load before proceeding
    await page.wait_for_load_state("networkidle")
    print("Page loaded, analyzing for CAPTCHA...")
    
    # Capture the CAPTCHA image for processing
    screenshot_bytes = await page.screenshot(full_page=True)
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    # PRIMARY METHOD: Get CAPTCHA text using the simplified approach
    # This is the main flow - other methods like get_multiple_captcha_solutions are not used
    captcha_text = await simple_captcha_solve(screenshot_base64)
    print(f"Detected CAPTCHA solution: {captcha_text}")
    
    # PHASE 1: Find the CAPTCHA input field by trying multiple selectors
    # This progressive approach handles different CAPTCHA UIs
    input_field = None
    for selector in [
        "input[type='text']",  # Most common input type
        "#captchacharacters",  # Amazon's specific CAPTCHA input ID
        "input.a-input-text",  # Amazon's class for text inputs
        "input.captcha-input", # Common CAPTCHA class
        "input[name*='captcha']", # Inputs with "captcha" in their name
        "input[id*='captcha']",  # Inputs with "captcha" in their ID
        "form input",  # Any input within a form (less specific)
        "input:not([type='hidden'])"  # Last resort: any visible input
    ]:
        try:
            input_field = await page.query_selector(selector)
            if input_field:
                print(f"Found CAPTCHA input field with selector: {selector}")
                break
        except Exception as e:
            # Silent error handling - just try the next selector
            continue
    
    # PHASE 2: Find the submit button by trying multiple selectors
    # Similar progressive approach for the submit button
    submit_button = None
    for selector in [
        "button[type='submit']",  # Standard submit button
        "input[type='submit']",   # Submit input (older sites)
        "button.a-button-input",  # Amazon's button class
        "input.a-button-input",   # Amazon's input button class
        "button:has-text('Continue')",  # Text-based button selection
        "button:has-text('Submit')",    # Text-based button selection
        ".a-button-input",        # Amazon's button class (less specific)
        "form button",            # Any button in a form
        "button",                 # Any button as last resort
        "[role='button']"         # Accessibility role as final fallback
    ]:
        try:
            submit_button = await page.query_selector(selector)
            if submit_button:
                print(f"Found submit button with selector: {selector}")
                break
        except Exception:
            # Silent error handling - just try the next selector
            continue
    
    # PHASE 3: Enter the CAPTCHA text into the input field
    # Multiple fallback strategies for entering text
    success = False
    if input_field:
        try:
            # Method 1: Clear and fill using Playwright's API
            await input_field.fill("")  # Clear first
            await input_field.type(captcha_text, delay=50)  # Type with human-like delay
            print(f"Entered CAPTCHA text: {captcha_text}")
            success = True
        except Exception:
            try:
                # Method 2: Manual selection and keyboard entry
                await input_field.click()
                await page.keyboard.press("Control+a")  # Select all existing text
                await page.keyboard.press("Delete")     # Delete selected text
                await page.keyboard.type(captcha_text)  # Type new text
                success = True
            except Exception:
                # Silent error - will try next approach
                pass
    
    # FALLBACK: If no input field found or entry failed, try clicking center of page
    if not success:
        try:
            # Calculate the center of the viewport
            viewport = page.viewport_size
            center_x = viewport["width"] // 2
            center_y = viewport["height"] // 2
            # Click in the center and type (sometimes works with focus-based forms)
            await page.mouse.click(center_x, center_y)
            await page.keyboard.type(captcha_text)
            success = True
        except Exception:
            # Silent error - will try next approach
            pass
    
    # PHASE 4: Submit the form
    if submit_button:
        try:
            # Method 1: Direct click
            await submit_button.click()
            print("Clicked submit button")
        except Exception:
            try:
                # Method 2: JavaScript click (works when elements are obscured)
                await page.evaluate("(button) => button.click()", submit_button)
            except Exception:
                # Method 3: Enter key as last resort
                await page.keyboard.press("Enter")
    else:
        # No button found, try Enter key
        await page.keyboard.press("Enter")
    
    # PHASE 5: Wait for the form submission to process
    # This delay allows the page to transition after submission
    await asyncio.sleep(3)
    
    # PHASE 6: Verify if we solved the CAPTCHA successfully
    # Check multiple indicators to see if we're still on the CAPTCHA page
    current_url = page.url
    current_title = await page.title()
    current_content = await page.content()
    
    # If any of these indicators are present, we're still on a CAPTCHA page
    still_captcha = (
        "captcha" in current_url.lower() or
        "robot check" in current_title.lower() or
        "captcha" in current_content.lower() or
        "robot check" in current_content.lower()
    )
    
    # Return a detailed result dictionary
    return {
        "text": captcha_text,  # The text we entered
        "success": not still_captcha,  # Success = no longer on CAPTCHA page
        "message": f"CAPTCHA {'solution attempt' if still_captcha else 'solved'} with text: {captcha_text}"
    }

async def simple_captcha_solve(image_base64: str) -> str:
    """
    PRIMARY CAPTCHA SOLVER: Simplified, robust approach that uses vision models
    to extract CAPTCHA text with specific Amazon CAPTCHA constraints.
    
    This is the MAIN method used in the current workflow.
    """
    client = OpenAI()
    
    try:
        # Use GPT-4o with vision capabilities to interpret the CAPTCHA
        # The prompt specifically mentions Amazon CAPTCHAs only use letters, not numbers
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert CAPTCHA solver. Extract ONLY the letters from the CAPTCHA image. Amazon CAPTCHAs ONLY use letters (A-Z), never numbers. Return ONLY the letters, no explanation."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": "Extract the CAPTCHA text from this image. Remember that Amazon CAPTCHAs only use letters (A-Z) and are exactly 6 uppercase letters in length, never numbers. ONLY return the letters, nothing else. For example: HEFXXO"
                        },
                        {
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                        }
                    ]
                }
            ],
            temperature=0.0  # Use deterministic output for consistency
        )
        
        # Process the model's output
        text = response.choices[0].message.content.strip()
        
        # CLEANING PHASE:
        # 1. Remove any non-letter characters (Amazon CAPTCHAs only use A-Z)
        text = re.sub(r'[^a-zA-Z]', '', text)
        
        # 2. Convert to uppercase (Amazon CAPTCHAs are uppercase)
        text = text.upper()
        
        # 3. Validate length (Amazon CAPTCHAs are typically 6 characters)
        if len(text) > 8:
            text = text[:8]  # Truncate if somehow too long
        elif len(text) < 4:
            # Warning for suspiciously short CAPTCHAs (likely didn't read correctly)
            print(f"Warning: Extracted CAPTCHA text is suspiciously short: '{text}'")
        
        # Return the cleaned CAPTCHA text if we extracted something
        if text:
            return text
    except Exception as e:
        print(f"Error in simple_captcha_solve: {e}")
    
    # FALLBACK: If everything fails, return a default set of letters
    # This is a last resort and likely won't solve the CAPTCHA
    return "doesnt look like anything to me"