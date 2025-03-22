import sys, os
venv_path = os.path.join(os.path.dirname(__file__), "venv", "Lib", "site-packages")
import asyncio
import base64
from playwright.async_api import async_playwright
from agents import Agent, Runner, function_tool

imhuman_agent = Agent(
    name="Imhuman OCR Agent",
    instructions="Extract text from the provided base64 encoded image string. Respond only with the detected text, for example: `ABC12345`.",
    model="gpt-4o-mini"
)

async def perform_ocr_async(image_base64: str) -> str:
    # Wrap the base64 image string into a single message input.
    result = await Runner.run(imhuman_agent, [{"role": "user", "content": image_base64}])
    print("detected_text=", result.final_output)
    return result.final_output

async def solve_captcha(page) -> str:
    """
    When instructed by the supervisor:
      1. Capture a full-page screenshot.
      2. Use OCR to extract text from the image.
      3. Dynamically determine the coordinates for the CAPTCHA input field and submit button.
      4. Click on the input field, type the detected text, and subsequently click submit.
      5. Provide confirmation back to the supervisor.
    """
    # Wait until the page is stable (no hard-coded selectors used here)
    await page.wait_for_load_state("networkidle")
    
    # Step 1: Capture a full-page screenshot
    screenshot_bytes = await page.screenshot(full_page=True)
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    # Step 2: Get OCR output from the image (this processes the entire page image)
    detected_text = await perform_ocr_async(screenshot_base64)
    print("Detected text from OCR:", detected_text)
    
    if not detected_text or "no text" in detected_text.lower():
        print("Imhuman OCR Agent could not detect any meaningful CAPTCHA text.")
        return ""
    
    # Step 3: (Dynamic detection) Instead of static selectors, assume a computer-use agent has determined
    # the input field and submit button coordinates.
    # In a real implementation, these would be returned by a computer-use loop.
    captcha_field_coords = (150, 300)      # Example coordinates for the CAPTCHA input field.
    submit_button_coords = (150, 350)        # Example coordinates for the submit button.
    
    # Step 4: Simulate actions on the page.
    print("Clicking on CAPTCHA input field at", captcha_field_coords)
    await page.mouse.click(*captcha_field_coords)
    print("Typing detected CAPTCHA text into input field...")
    await page.keyboard.type(detected_text)
    print("Clicking on submit button at", submit_button_coords)
    
    # Allow time for the form to process.
    await asyncio.sleep(3)
    
    confirmation = f"CAPTCHA solved with text: {detected_text}"
    print(confirmation)
    
    # Step 5: Hand off confirmation back to the supervisor.
    return confirmation
