from agents import Agent, Runner
import asyncio
import base64

imhuman_agent = Agent(
    name="Imhuman OCR Agent",
    instructions="Extract text from the provided base64 encoded image string. Respond only with the detected text, for example: `ABC12345`.",
    model="gpt-4o-mini"
)

async def perform_ocr_async(image_base64: str) -> str:
    result = await Runner.run(imhuman_agent, image_base64)
    return result.final_output

async def solve_captcha(page) -> str:
    # Check for CAPTCHA using the known input id
    captcha_input = await page.query_selector("input#captchacharacters")
    if captcha_input:
        captcha_image = await page.query_selector("img[src*='captcha']")
        if captcha_image:
            screenshot_bytes = await captcha_image.screenshot()
            image_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            detected_text = await perform_ocr_async(image_base64)
            if detected_text:
                # fill in the search text input
                await captcha_input.fill(detected_text)
                submit_button = await page.query_selector("button[type='submit'], input[type='submit'], a[onclick*='reload']")
                if submit_button:
                    await submit_button.click()
                await asyncio.sleep(3)  # wait for CAPTCHA to be processed
                return detected_text
            else:
                print("Imhuman OCR Agent failed to detect CAPTCHA text.")
        else:
            print("CAPTCHA image not found.")
    return None
