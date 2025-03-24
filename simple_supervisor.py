import os
import asyncio
import base64
import json
from openai import OpenAI
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from imhuman import solve_captcha
from mango_finder_agent import mango_finder_agent
from select_item_agent import select_item_agent

async def simple_supervisor():
    """
    An enhanced supervisor agent that:
    1. Opens amazon.com
    2. Takes a screenshot
    3. Analyzes the situation and delegates to specialized agents:
       - imhuman agent for CAPTCHAs
       - mango_finder_agent for searching products
       - select_item_agent for choosing products (future)
    """
    # Load environment variables and initialize OpenAI client
    load_dotenv()
    client = OpenAI()
    
    # Set up browser with Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1024, "height": 768})
        
        try:
            # Step 1: Navigate to Amazon.com
            print("Navigating to Amazon.com...")
            await page.goto("https://www.amazon.com")
            await page.wait_for_load_state("networkidle", timeout=30000)
            
            # Loop to handle multiple interactions
            max_interactions = 10
            interaction_count = 0
            mango_finder_invoked = False
            select_item_invoked = False
            
            while interaction_count < max_interactions:
                interaction_count += 1
                
                # Take a screenshot of the current page
                print(f"Taking screenshot (interaction {interaction_count})...")
                screenshot_bytes = await page.screenshot(full_page=True)
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                
                # Get page title and URL to help with state detection
                page_title = await page.title()
                page_url = page.url
                page_content = await page.content()
                
                # Improved CAPTCHA detection with multiple methods
                captcha_detected = (
                    "captcha" in page_url.lower() or 
                    "robot check" in page_title.lower() or 
                    "verify" in page_title.lower() or
                    "captcha" in page_content.lower() or
                    "robot check" in page_content.lower() or
                    "solve this puzzle" in page_content.lower()
                )
                
                if captcha_detected:
                    print("\n----- CAPTCHA DETECTED -----")
                    print("Invoking imhuman agent to solve CAPTCHA...")
                    
                    # Store pre-CAPTCHA state for comparison
                    pre_captcha_url = page.url
                    pre_captcha_title = await page.title()
                    
                    # Call the imhuman agent to solve the CAPTCHA
                    captcha_result = await solve_captcha(page)
                    print(f"CAPTCHA solution attempt: {captcha_result}")
                    
                    # Wait for page to load after CAPTCHA solution
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    
                    # Verify if CAPTCHA was truly solved by checking if page changed
                    post_captcha_url = page.url
                    post_captcha_title = await page.title()
                    new_page_content = await page.content()
                    
                    # Check if we're still on a CAPTCHA page
                    still_captcha = (
                        post_captcha_url == pre_captcha_url and 
                        post_captcha_title == pre_captcha_title or
                        "captcha" in new_page_content.lower() or
                        "robot check" in new_page_content.lower()
                    )
                    
                    if still_captcha:
                        print("⚠️ CAPTCHA solution appears to have failed. Page didn't change.")
                        # Take a new screenshot for analysis
                        new_screenshot_bytes = await page.screenshot(full_page=True)
                        new_screenshot_base64 = base64.b64encode(new_screenshot_bytes).decode("utf-8")
                        
                        # Ask GPT to verify if we're still on a CAPTCHA page
                        verify_response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "You are analyzing a webpage to determine if it's still showing a CAPTCHA challenge after an attempted solution."
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": "Does this page still show a CAPTCHA challenge or error message? Answer with YES or NO and explain briefly."},
                                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{new_screenshot_base64}"}}
                                    ]
                                }
                            ],
                            max_tokens=100
                        )
                        
                        verification = verify_response.choices[0].message.content
                        print(f"CAPTCHA verification: {verification}")
                        
                        if "YES" in verification.upper():
                            print("Confirmed: CAPTCHA still present. Will retry in next iteration.")
                        else:
                            print("False alarm: CAPTCHA appears to be solved despite unchanged URL.")
                            # Continue with normal flow
                    else:
                        print("✅ CAPTCHA appears to be solved successfully! Page changed.")
                    
                    continue  # Take a new screenshot and reassess
                
                # Send to OpenAI for analysis using GPT-4 Vision to decide next action
                print("Analyzing screenshot with OpenAI to decide next action...")
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a supervisor agent that analyzes Amazon screenshots and decides the best next action. "
                                "Your goal is to help order mango slices from Amazon. "
                                "Based on what you see, choose ONE of these actions:\n"
                                "1. USE_IMHUMAN: If you see a CAPTCHA or robot check, even if it's subtle or hidden\n"
                                "2. USE_MANGO_FINDER: If you need to search for mango slices\n"
                                "3. USE_ITEM_SELECTOR: If you see search results and need to select a product\n"
                                "4. FINISHED: If the goal has been achieved (product added to cart/checkout started)\n"
                                "Look carefully for any signs of a security challenge or CAPTCHA before proceeding."
                                "Respond with ONLY ONE of these action codes and a brief explanation."
                            )
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Analyze this Amazon page and decide the next action to take for ordering mango slices:"},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"}}
                            ]
                        }
                    ],
                    max_tokens=150
                )
                
                # Extract the recommendation
                decision = response.choices[0].message.content
                print("\n----- SUPERVISOR DECISION -----")
                print(decision)
                print("-------------------------------------\n")
                
                # Process the decision
                if "USE_IMHUMAN" in decision:
                    print("Supervisor detected possible CAPTCHA. Invoking imhuman agent...")
                    await solve_captcha(page)
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    
                elif "USE_MANGO_FINDER" in decision:
                    print("\n----- INVOKING MANGO FINDER AGENT -----")
                    print("Delegating search task to specialized mango finder agent...")
                    mango_finder_invoked = True
                    
                    # Call the mango finder agent to search for mangos
                    mango_result = await mango_finder_agent(page)
                    
                    print(f"Mango finder agent completed with status: {mango_result['status']}")
                    print(f"Current URL: {mango_result['url']}")
                    print(f"Method used: {mango_result.get('method', 'unknown')}")
                    
                    if mango_result['status'] == 'complete':
                        print("Successfully found mango products!")
                    else:
                        print("Mango finder had trouble completing the task.")
                        
                        # Check if we might have hit a CAPTCHA
                        post_search_content = await page.content()
                        if ("captcha" in post_search_content.lower() or 
                            "robot" in post_search_content.lower()):
                            print("Possible CAPTCHA detected after mango search. Will check in next iteration.")
                    
                    # Wait for page to stabilize after mango finder actions
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    
                elif "USE_ITEM_SELECTOR" in decision and not select_item_invoked:
                    print("\n----- INVOKING ITEM SELECTOR AGENT -----")
                    select_item_invoked = True
                    
                    # Call the item selector agent to pick a product
                    selection_result = await select_item_agent(page)
                    
                    print(f"Item selector completed with status: {selection_result['status']}")
                    print(f"Product page reached: {selection_result.get('product_page', False)}")
                    
                    # Wait for page to stabilize after selection
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    
                elif "FINISHED" in decision:
                    print("\n----- GOAL ACHIEVED -----")
                    print("Supervisor determined the goal has been achieved!")
                    break
                
                # Check if we've accomplished a sub-goal
                if not mango_finder_invoked and ("s?k=mango" in page_url or "mango" in page_url.lower()):
                    print("Search results detected - we can skip the mango finder step.")
                    mango_finder_invoked = True
                
                if not select_item_invoked and "/dp/" in page_url:
                    print("Product page detected - we can skip the item selection step.")
                    select_item_invoked = True
                
                # Ask if the user wants to continue or take manual action
                print("\nContinue to next interaction? Press Enter or type 'exit' to stop:")
                user_input = await asyncio.get_event_loop().run_in_executor(None, input)
                if user_input.lower() == "exit":
                    break
            
            # Wait for user to press Enter before closing
            print("\nWorkflow completed. Press Enter to close the browser...")
            await asyncio.get_event_loop().run_in_executor(None, input)
            
        except Exception as e:
            print(f"Error in supervisor workflow: {e}")
            # Take error screenshot
            error_screenshot = await page.screenshot()
            error_path = "error_screenshot.png"
            with open(error_path, "wb") as f:
                f.write(error_screenshot)
            print(f"Error screenshot saved to {error_path}")
        
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(simple_supervisor())
