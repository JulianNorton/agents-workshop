import sys, os
import asyncio
import base64
import json
import re
from typing import List, Dict, Tuple, Optional, Union
from playwright.async_api import Page
from agents import Agent, Runner
from openai import OpenAI

# Simplified OCR agent that focuses specifically on extracting CAPTCHA text
captcha_ocr_agent = Agent(
    name="CAPTCHA OCR Agent",
    instructions="You are an expert at solving CAPTCHAs. Examine the image and extract ONLY the CAPTCHA characters or text. Return ONLY the characters with no additional text or explanations.",
    model="gpt-4o"  # Using the most capable model for CAPTCHA solving
)

async def solve_captcha(page: Page) -> Dict:
    """
    Simplified CAPTCHA solver with robust error handling
    """
    # Wait for the page to load completely
    await page.wait_for_load_state("networkidle")
    print("Page loaded, analyzing for CAPTCHA...")
    
    # Take a screenshot for analysis
    screenshot_bytes = await page.screenshot(full_page=True)
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    # Get CAPTCHA text using simplified approach
    captcha_text = await simple_captcha_solve(screenshot_base64)
    print(f"Detected CAPTCHA solution: {captcha_text}")
    
    # Find input field
    input_field = None
    for selector in [
        "input[type='text']", 
        "#captchacharacters", 
        "input.a-input-text", 
        "input.captcha-input",
        "input[name*='captcha']",
        "input[id*='captcha']",
        "form input", 
        "input:not([type='hidden'])" 
    ]:
        try:
            input_field = await page.query_selector(selector)
            if input_field:
                print(f"Found CAPTCHA input field with selector: {selector}")
                break
        except Exception as e:
            continue
    
    # Find submit button
    submit_button = None
    for selector in [
        "button[type='submit']", 
        "input[type='submit']",
        "button.a-button-input",
        "input.a-button-input",
        "button:has-text('Continue')",
        "button:has-text('Submit')",
        ".a-button-input",
        "form button", 
        "button", 
        "[role='button']" 
    ]:
        try:
            submit_button = await page.query_selector(selector)
            if submit_button:
                print(f"Found submit button with selector: {selector}")
                break
        except Exception:
            continue
    
    # Enter the CAPTCHA text
    success = False
    if input_field:
        try:
            await input_field.fill("")
            await input_field.type(captcha_text, delay=50)
            print(f"Entered CAPTCHA text: {captcha_text}")
            success = True
        except Exception:
            try:
                await input_field.click()
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Delete")
                await page.keyboard.type(captcha_text)
                success = True
            except Exception:
                pass
    
    if not success:
        # Try clicking in the center and typing
        try:
            viewport = page.viewport_size
            center_x = viewport["width"] // 2
            center_y = viewport["height"] // 2
            await page.mouse.click(center_x, center_y)
            await page.keyboard.type(captcha_text)
            success = True
        except Exception:
            pass
    
    # Submit the form
    if submit_button:
        try:
            await submit_button.click()
            print("Clicked submit button")
        except Exception:
            try:
                await page.evaluate("(button) => button.click()", submit_button)
            except Exception:
                await page.keyboard.press("Enter")
    else:
        await page.keyboard.press("Enter")
    
    # Wait briefly
    await asyncio.sleep(3)
    
    # Check if we're still on a CAPTCHA page
    current_url = page.url
    current_title = await page.title()
    current_content = await page.content()
    
    still_captcha = (
        "captcha" in current_url.lower() or
        "robot check" in current_title.lower() or
        "captcha" in current_content.lower() or
        "robot check" in current_content.lower()
    )
    
    return {
        "text": captcha_text,
        "success": not still_captcha,
        "message": f"CAPTCHA {'solution attempt' if still_captcha else 'solved'} with text: {captcha_text}"
    }

async def simple_captcha_solve(image_base64: str) -> str:
    """Simplified CAPTCHA solver that's more robust to API changes"""
    client = OpenAI()
    
    try:
        # Try direct vision analysis with simple prompt
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
                            "text": "Extract the CAPTCHA text from this image. Remember that Amazon CAPTCHAs only use letters (A-Z), never numbers. ONLY return the letters, nothing else."
                        },
                        {
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                        }
                    ]
                }
            ],
            temperature=0.0
        )
        
        text = response.choices[0].message.content.strip()
        # Clean extremely aggressively - allow ONLY letters A-Z
        text = re.sub(r'[^a-zA-Z]', '', text)
        
        # Convert to uppercase as Amazon CAPTCHAs are typically uppercase
        text = text.upper()
        
        # Validate length - Amazon CAPTCHAs are typically 6 characters
        if len(text) > 8:
            text = text[:8]  # Truncate if somehow too long
        elif len(text) < 4:
            print(f"Warning: Extracted CAPTCHA text is suspiciously short: '{text}'")
        
        if text:
            return text
    except Exception as e:
        print(f"Error in simple_captcha_solve: {e}")
    
    # If we get here, something failed - return a fallback of 6 uppercase letters
    return "ABCDEF"

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
                    "content": "You are an expert CAPTCHA solver. Analyze the image and provide the 3 most likely solutions for the CAPTCHA with confidence percentages. Amazon CAPTCHAs only use letters (A-Z), never numbers. Return your answer as a JSON array with objects containing 'text' and 'confidence' fields."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "What are the 3 most likely solutions for this Amazon CAPTCHA? Remember it only uses letters, not numbers. Provide each potential solution with a confidence percentage."},
                        {"type": "input_image", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
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
        
        # After extraction, additionally filter solutions to ensure they contain only letters
        for i, (solution, confidence) in enumerate(solutions):
            cleaned_solution = re.sub(r'[^a-zA-Z]', '', solution).upper()
            if cleaned_solution != solution:
                solutions[i] = (cleaned_solution, confidence)
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
                        {"type": "input_text", "text": "Analyze this CAPTCHA character by character. For each position, what is the most likely character and your confidence?"},
                        {"type": "input_image", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
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
                    {"type": "input_text", "text": "Extract the CAPTCHA text from this image. Return ONLY the characters."},
                    {"type": "input_image", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
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
                        {"type": "input_text", "text": "Find the x,y coordinates of: 1) The CAPTCHA input field, 2) The submit button. Return a JSON object with 'input_field' and 'submit_button' properties, each containing 'x' and 'y' coordinates."},
                        {"type": "input_image", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
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
                    "content": "Extract ONLY the letters visible in the Amazon CAPTCHA image. Amazon CAPTCHAs only use letters (A-Z), never numbers. NO explanations, ONLY the UPPERCASE letters."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "What letters do you see in this Amazon CAPTCHA? Remember it only contains letters, not numbers."},
                        {"type": "input_image", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                    ]
                }
            ]
        )
        
        text = response.choices[0].message.content
        # Clean extremely aggressively - only allow letters
        text = re.sub(r'[^a-zA-Z]', '', text)
        text = text.strip().upper()
        
        # Validate typical Amazon CAPTCHA length
        if len(text) > 8:
            text = text[:8]  # Truncate if somehow too long
            
        print(f"Emergency OCR extracted: {text}")
        return text
    except Exception as e:
        print(f"Emergency OCR failed: {e}")
        # Return a fallback response using only letters
        return "doesnt look like anything to me"
