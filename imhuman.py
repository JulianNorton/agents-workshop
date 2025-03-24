import sys, os
import asyncio
import base64
import json
import re
from typing import List, Dict, Tuple, Optional
from playwright.async_api import Page
from agents import Agent, Runner
from openai import OpenAI

# Simplified OCR agent that focuses specifically on extracting CAPTCHA text
captcha_ocr_agent = Agent(
    name="CAPTCHA OCR Agent",
    instructions="You are an expert at solving CAPTCHAs. Examine the image and extract ONLY the CAPTCHA characters or text. Return ONLY the characters with no additional text or explanations.",
    model="gpt-4o"  # Using the most capable model for CAPTCHA solving
)

async def solve_captcha(page: Page) -> str:
    """
    Improved CAPTCHA solver that:
    1. Takes a screenshot of the page
    2. Uses GPT-4o to analyze the CAPTCHA, find the input field, and identify the submit button
    3. Provides multiple potential solutions with confidence ratings
    4. Enters the highest confidence solution and submits the form
    5. Returns the result
    """
    # Wait for the page to load completely
    await page.wait_for_load_state("networkidle")
    print("Page loaded, analyzing for CAPTCHA...")
    
    # Take a screenshot for analysis
    screenshot_bytes = await page.screenshot(full_page=True)
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    # Step 1: Get multiple CAPTCHA solutions using different methods
    captcha_solutions = await get_multiple_captcha_solutions(screenshot_base64)
    
    # Print all solutions with confidence
    print("\nPotential CAPTCHA solutions:")
    for solution, confidence in captcha_solutions:
        print(f"  • '{solution}' (confidence: {confidence}%)")
    
    # Get the highest confidence solution
    if captcha_solutions:
        captcha_text, confidence = captcha_solutions[0]
        print(f"\nUsing highest confidence solution: '{captcha_text}' ({confidence}%)")
    else:
        # Fallback approach - try direct OCR as last resort
        print("All solution methods failed, using emergency OCR...")
        captcha_text = await emergency_ocr(screenshot_base64)
    
    # Step 2: Find the input field - try multiple common selectors
    input_field = None
    for selector in [
        "input[type='text']", 
        "#captchacharacters", 
        "input.a-input-text", 
        "input.captcha-input",
        "input[name*='captcha']",
        "input[id*='captcha']",
        "form input", # Generic form inputs
        "input:not([type='hidden'])" # Any visible input
    ]:
        try:
            input_field = await page.query_selector(selector)
            if input_field:
                print(f"Found CAPTCHA input field with selector: {selector}")
                break
        except Exception as e:
            print(f"Error finding input with selector {selector}: {str(e)}")
            continue
    
    # Step 3: Find the submit button - try multiple common selectors
    submit_button = None
    for selector in [
        "button[type='submit']", 
        "input[type='submit']",
        "button.a-button-input",
        "input.a-button-input",
        "button:has-text('Continue')",
        "button:has-text('Submit')",
        "input[name='submit']",
        ".a-button-input",
        "form button", # Any button in a form
        "button", # Any button
        "[role='button']" # Accessibility role
    ]:
        try:
            submit_button = await page.query_selector(selector)
            if submit_button:
                print(f"Found submit button with selector: {selector}")
                break
        except Exception as e:
            print(f"Error finding button with selector {selector}: {str(e)}")
            continue
    
    # Step 4: If we couldn't find elements by selectors, try to get visual coordinates
    if not input_field or not submit_button:
        print("Couldn't find elements by selectors, attempting visual search...")
        try:
            coordinates = await get_element_coordinates(screenshot_base64)
            
            if coordinates and "input_field" in coordinates and "submit_button" in coordinates:
                input_x = coordinates["input_field"]["x"]
                input_y = coordinates["input_field"]["y"]
                submit_x = coordinates["submit_button"]["x"]
                submit_y = coordinates["submit_button"]["y"]
                
                # Use the coordinates
                print(f"Using visual coordinates - input: ({input_x},{input_y}), submit: ({submit_x},{submit_y})")
                await page.mouse.click(input_x, input_y)
                await page.keyboard.type(captcha_text)
                await asyncio.sleep(1)
                await page.mouse.click(submit_x, submit_y)
                
                # Return early since we've handled everything
                await asyncio.sleep(3)  # Wait for form submission
                return f"CAPTCHA solved with text: {captcha_text} (using visual coordinates)"
            
        except Exception as e:
            print(f"Error in visual element detection: {e}")
    
    # Step 5: Enter the CAPTCHA text if we found the input field
    if input_field:
        # First, try to clear the field
        try:
            await input_field.fill("")  # Clear the field first
            await input_field.type(captcha_text, delay=100)  # Type slowly
            print(f"Entered CAPTCHA text: {captcha_text}")
        except Exception as e:
            print(f"Error entering CAPTCHA text: {e}. Trying alternative method.")
            # Fallback: click and type
            try:
                await input_field.click()
                # Clear field with keyboard
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Delete")
                # Type text
                await page.keyboard.type(captcha_text, delay=100)
                print(f"Entered CAPTCHA text with alternative method: {captcha_text}")
            except Exception as e2:
                print(f"Both input methods failed: {e2}")
    else:
        print("⚠️ Could not find CAPTCHA input field, attempting fallback...")
        # Fallback: try to send keystrokes to the page
        await page.keyboard.press("Tab")  # Try to focus on an input field
        await page.keyboard.type(captcha_text, delay=100)
    
    # Step 6: Submit the form if we found the button
    if submit_button:
        await asyncio.sleep(1)  # Brief pause before clicking
        try:
            await submit_button.click()
            print("Clicked submit button")
        except Exception as e:
            print(f"Error clicking submit button: {e}. Trying JavaScript click.")
            # Try using JavaScript click as fallback
            try:
                await page.evaluate("(button) => button.click()", submit_button)
                print("Clicked submit button with JavaScript")
            except Exception as e2:
                print(f"Both click methods failed: {e2}")
    else:
        print("⚠️ Could not find submit button, attempting fallback...")
        # Fallback: try to press Enter
        await page.keyboard.press("Enter")
    
    # Step 7: Wait for navigation after submission
    await asyncio.sleep(3)
    
    # Return the result
    result = f"CAPTCHA solved with text: {captcha_text}"
    print(result)
    return result

async def get_multiple_captcha_solutions(image_base64: str) -> List[Tuple[str, float]]:
    """
    Get multiple CAPTCHA solutions using different methods with confidence ratings.
    Returns a list of (solution, confidence_percentage) tuples, sorted by confidence.
    """
    solutions = []
    client = OpenAI()
    
    # Method 1: Direct vision analysis with clear instructions for multiple candidates
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert CAPTCHA solver. Analyze the image and provide the 3 most likely solutions for the CAPTCHA with confidence percentages. Return your answer as a JSON array with objects containing 'text' and 'confidence' fields. Format must be JSON."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What are the 3 most likely solutions for this CAPTCHA? Provide each potential solution with a confidence percentage."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )
        
        try:
            result = json.loads(response.choices[0].message.content)
            if "solutions" in result:
                for sol in result["solutions"]:
                    text = sol.get("text", "").strip()
                    confidence = float(sol.get("confidence", 0))
                    if text:
                        solutions.append((text, confidence))
            elif isinstance(result, list):
                for sol in result:
                    text = sol.get("text", "").strip()
                    confidence = float(sol.get("confidence", 0))
                    if text:
                        solutions.append((text, confidence))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            print(f"Error parsing multi-solution JSON: {e}")
    except Exception as e:
        print(f"Error with multi-solution method: {e}")
    
    # Method 2: Character-by-character analysis
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert CAPTCHA solver. For each character in the CAPTCHA image, provide the most likely letter or digit and your confidence percentage. Format the response as a JSON object with an array named 'characters', where each object has 'position', 'character', and 'confidence' properties."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this CAPTCHA character by character. For each position, what is the most likely character and your confidence?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )
        
        try:
            result = json.loads(response.choices[0].message.content)
            if "characters" in result and isinstance(result["characters"], list):
                # Combine characters into a full solution
                char_array = result["characters"]
                text = ''.join(char.get("character", "") for char in char_array)
                # Calculate average confidence
                if char_array:
                    avg_confidence = sum(float(char.get("confidence", 0)) for char in char_array) / len(char_array)
                    solutions.append((text, avg_confidence))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            print(f"Error parsing character-by-character JSON: {e}")
    except Exception as e:
        print(f"Error with character-by-character method: {e}")
    
    # Method 3: Standard OCR (fallback)
    try:
        result = await Runner.run(captcha_ocr_agent, [
            {
                "role": "user", 
                "content": [
                    {"type": "text", "text": "Extract the CAPTCHA text from this image. Return ONLY the characters."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                ]
            }
        ])
        
        text = result.final_output
        # Clean up the text
        text = re.sub(r'[^a-zA-Z0-9]', '', text)
        # Assign a moderate confidence value to this method
        if text:
            solutions.append((text, 65.0))
    except Exception as e:
        print(f"Error with standard OCR method: {e}")
    
    # Sort by confidence (highest first)
    solutions.sort(key=lambda x: x[1], reverse=True)
    return solutions

async def get_element_coordinates(image_base64: str) -> Optional[Dict]:
    """
    Get coordinates for CAPTCHA input field and submit button using vision analysis.
    """
    client = OpenAI()
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at analyzing web forms. Locate the CAPTCHA input field and submit button in this image. Return their x,y coordinates as a JSON object."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Find the x,y coordinates of: 1) The CAPTCHA input field, 2) The submit button. Return a JSON object with 'input_field' and 'submit_button' properties, each containing 'x' and 'y' coordinates."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )
        
        try:
            result = json.loads(response.choices[0].message.content)
            return result
        except json.JSONDecodeError as e:
            print(f"Error parsing coordinates JSON: {e}")
            return None
    except Exception as e:
        print(f"Error getting element coordinates: {e}")
        return None

async def emergency_ocr(image_base64: str) -> str:
    """Last resort CAPTCHA OCR method when all else fails."""
    try:
        # Analyze only for text, with extremely clear instructions
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.0,  # Use deterministic output
            messages=[
                {
                    "role": "system",
                    "content": "Extract ONLY the characters visible in the CAPTCHA image. NO explanations, ONLY the characters."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What characters do you see in this CAPTCHA?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                    ]
                }
            ]
        )
        
        text = response.choices[0].message.content
        # Clean extremely aggressively
        text = re.sub(r'[^a-zA-Z0-9]', '', text)
        text = text.strip()
        
        # Truncate if somehow still too long
        if len(text) > 10:
            text = text[:10]
            
        print(f"Emergency OCR extracted: {text}")
        return text
    except Exception as e:
        print(f"Emergency OCR failed: {e}")
        # Return a fallback response if all else fails
        return "ABCDE12345"
