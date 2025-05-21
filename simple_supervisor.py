import os
import asyncio
import base64
import json
import time
from typing import Dict, Any
from openai import OpenAI
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
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
            
            # Use a more robust wait approach
            await wait_for_page_with_fallback(page, "networkidle", timeout=10000)
            
            # Loop to handle multiple interactions
            max_interactions = 10
            interaction_count = 0
            mango_finder_invoked = False
            select_item_invoked = False
            captcha_just_solved = False  # Track if we just solved a CAPTCHA
            captcha_attempts = 0  # Track consecutive CAPTCHA attempts
            
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
                
                # Check if we're on the Amazon search results page after finding mangos
                on_search_results = (
                    "amazon.com" in page_url and 
                    ("s?k=mango" in page_url or "mango" in page_url.lower()) and
                    not captcha_detected and
                    mango_finder_invoked and
                    not select_item_invoked
                )
                
                # Check if we're on a product detail page
                on_product_page = "/dp/" in page_url and not captcha_detected
                
                # Check if we're already on the cart page
                on_cart_page = "cart" in page_url.lower() and "amazon.com" in page_url
                
                # Auto-trigger item selection if we're on search results
                if on_search_results:
                    print("\n----- ON MANGO SEARCH RESULTS PAGE -----")
                    print("Automatically proceeding to product selection...")
                    
                    # Call the item selector agent to pick a product
                    selection_result = await select_item_agent(page)
                    select_item_invoked = True
                    
                    print(f"Item selector completed with status: {selection_result['status']}")
                    if "product_page" in selection_result:
                        print(f"Product page reached: {selection_result['product_page']}")
                    if "cart_added" in selection_result:
                        print(f"Added to cart: {selection_result['cart_added']}")
                    
                    # Wait for page to stabilize after selection
                    await wait_for_page_with_fallback(page, "networkidle", timeout=10000)
                    continue  # Take a new screenshot and reassess
                
                # Check if we're on the Amazon homepage after solving a CAPTCHA
                on_amazon_homepage = (
                    "amazon.com" in page_url and 
                    not captcha_detected and
                    (page_url == "https://www.amazon.com/" or 
                     page_url == "https://www.amazon.com" or
                     "nav_logo" in page_content)
                )
                
                # If we just solved a CAPTCHA and now we're on the Amazon homepage, go directly to mango search
                if (captcha_just_solved or captcha_attempts > 0) and on_amazon_homepage and not mango_finder_invoked:
                    print("\n----- CAPTCHA SOLVED, NOW ON AMAZON HOMEPAGE -----")
                    print("Directly proceeding to mango search...")
                    
                    # Reset CAPTCHA tracking
                    captcha_just_solved = False
                    captcha_attempts = 0
                    
                    # Call the mango finder agent to search for mangos
                    mango_result = await mango_finder_agent(page)
                    mango_finder_invoked = True
                    
                    print(f"Mango finder agent completed with status: {mango_result['status']}")
                    print(f"Current URL: {mango_result['url']}")
                    
                    # Wait for page to stabilize after mango finder actions - use robust wait
                    await wait_for_page_with_fallback(page, "networkidle", timeout=10000)
                    continue  # Take a new screenshot and reassess
                
                if captcha_detected:
                    print("\n----- CAPTCHA DETECTED -----")
                    print("Invoking imhuman agent to solve CAPTCHA...")
                    captcha_attempts += 1
                    
                    # Store pre-CAPTCHA state for comparison
                    pre_captcha_url = page.url
                    pre_captcha_title = await page.title()
                    
                    # Call the imhuman agent to solve the CAPTCHA
                    captcha_result = await solve_captcha(page)
                    
                    # Enhanced handling of CAPTCHA result
                    if isinstance(captcha_result, dict):
                        print(f"CAPTCHA solution attempt: {captcha_result.get('message', 'No message')}")
                        captcha_just_solved = captcha_result.get('success', False)
                    else:
                        # For backwards compatibility
                        print(f"CAPTCHA solution attempt: {captcha_result}")
                        
                        # Wait for a shorter time to let any navigation start
                        await asyncio.sleep(2)
                        
                        # Check if page changed after CAPTCHA solution
                        post_captcha_url = page.url
                        post_captcha_title = await page.title()
                        captcha_just_solved = (
                            post_captcha_url != pre_captcha_url or 
                            post_captcha_title != pre_captcha_title
                        )
                    
                    # Try a more patient approach to waiting for load
                    print("Waiting for page to stabilize after CAPTCHA submission...")
                    try:
                        await wait_for_page_with_fallback(page, "networkidle", timeout=10000)
                        print("Page stabilized after CAPTCHA submission")
                    except Exception as e:
                        print(f"Warning: Timeout waiting for page stabilization: {e}")
                        # Continue anyway - don't let a timeout stop us
                    
                    # Check current state again
                    current_url = page.url
                    current_title = await page.title()
                    current_content = await page.content()
                    
                    still_captcha = (
                        "captcha" in current_url.lower() or
                        "robot check" in current_title.lower() or
                        "captcha" in current_content.lower() or
                        "robot check" in current_content.lower()
                    )
                    
                    if still_captcha:
                        print("⚠️ Still on CAPTCHA page after solution attempt")
                        captcha_just_solved = False
                    else:
                        print("✅ No longer on CAPTCHA page - solution appears successful")
                        captcha_just_solved = True
                        
                        # If we're on Amazon homepage, immediately trigger mango finder in next iteration
                        if "amazon.com" in current_url and not "s?k=" in current_url:
                            print("Detected Amazon homepage - will search for mangos in next iteration")
                    
                    continue  # Take a new screenshot and reassess
                
                # Determine if this is the Amazon homepage (for clearer decision-making)
                is_amazon_homepage = (
                    "amazon.com" in page_url and 
                    not "s?k=" in page_url and
                    not "/dp/" in page_url
                )
                
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
                                f"Current state: {'Amazon homepage' if is_amazon_homepage else 'Amazon page'}, "
                                f"CAPTCHA just solved: {captcha_just_solved}, "
                                f"Search already performed: {mango_finder_invoked}, "
                                f"Product selection already performed: {select_item_invoked}\n\n"
                                "Based on what you see, choose ONE of these actions:\n"
                                "1. USE_IMHUMAN: If you see a CAPTCHA or robot check\n"
                                "2. USE_MANGO_FINDER: If you're on the Amazon homepage or need to search for mango slices\n"
                                "3. USE_ITEM_SELECTOR: If you see search results and need to select a product\n"
                                "4. FINISHED: If the goal has been achieved (product selected or added to cart)\n"
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
                    await wait_for_page_with_fallback(page, "networkidle", timeout=10000)
                    captcha_just_solved = True
                    
                elif "USE_MANGO_FINDER" in decision:
                    print("\n----- INVOKING MANGO FINDER AGENT -----")
                    print("Delegating search task to specialized mango finder agent...")
                    
                    # Call the mango finder agent to search for mangos
                    mango_result = await mango_finder_agent(page)
                    mango_finder_invoked = True
                    captcha_just_solved = False  # Reset the flag
                    
                    print(f"Mango finder agent completed with status: {mango_result['status']}")
                    print(f"Current URL: {mango_result['url']}")
                    
                    if mango_result['status'] == 'complete':
                        print("Successfully found mango products!")
                    else:
                        print("Mango finder had trouble completing the task.")
                        
                        # Check if we might have hit a CAPTCHA
                        post_search_content = await page.content()
                        if ("captcha" in post_search_content.lower() or 
                            "robot" in post_search_content.lower()):
                            print("Possible CAPTCHA detected after mango search.")
                            captcha_just_solved = False
                    
                    # Wait for page to stabilize after mango finder actions
                    await wait_for_page_with_fallback(page, "networkidle", timeout=10000)
                    
                elif "USE_ITEM_SELECTOR" in decision:
                    print("\n----- INVOKING ITEM SELECTOR AGENT -----")
                    
                    # Call the item selector agent to pick a product
                    selection_result = await select_item_agent(page)
                    select_item_invoked = True
                    captcha_just_solved = False  # Reset the flag
                    
                    print(f"Item selector completed with status: {selection_result['status']}")
                    if "product_page" in selection_result:
                        print(f"Product page reached: {selection_result['product_page']}")
                    if "cart_added" in selection_result:
                        print(f"Added to cart: {selection_result['cart_added']}")
                    
                    # Wait for page to stabilize after selection
                    await wait_for_page_with_fallback(page, "networkidle", timeout=10000)
                    
                # Verify cart contents if goal appears to be achieved or select_item_agent was invoked
                if select_item_invoked and not on_cart_page and "FINISHED" in decision:
                    print("\n----- VERIFYING GOAL ACHIEVEMENT -----")
                    print("Navigating to cart to verify mango product was added...")
                    
                    # Navigate to the Amazon cart page
                    try:
                        await page.goto("https://www.amazon.com/gp/cart/view.html?ref_=nav_cart")
                        await wait_for_page_with_fallback(page, "networkidle", timeout=10000)
                        
                        # Take screenshot of cart
                        cart_screenshot = await page.screenshot(full_page=True)
                        cart_screenshot_base64 = base64.b64encode(cart_screenshot).decode("utf-8")
                        
                        # Check if cart has mango products
                        cart_page_content = await page.content()
                        cart_verification = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "Verify if there are any mango products in this Amazon shopping cart. Answer only YES or NO, followed by a brief explanation."
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": "Does this Amazon cart contain any mango products?"},
                                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{cart_screenshot_base64}"}}
                                    ]
                            }
                            ],
                            max_tokens=100
                        )
                        
                        cart_check_result = cart_verification.choices[0].message.content
                        print(f"Cart verification result: {cart_check_result}")
                        
                        # Check if cart has items (based on both vision model and page content)
                        cart_has_mangos = "YES" in cart_check_result.upper() or (
                            "mango" in cart_page_content.lower() and 
                            not "empty" in cart_page_content.lower() and
                            not "was removed" in cart_page_content.lower()
                        )
                        
                        if cart_has_mangos:
                            print("✅ SUCCESS: Mango product confirmed in cart!")
                            return_to_previous_page = False  # Stay on cart page as we're done
                            break  # Exit the loop as we've achieved our goal
                        else:
                            print("❌ FAILURE: No mango products found in cart!")
                            print("Returning to previous page to try again...")
                            await page.goto(page_url)  # Return to previous page
                            await wait_for_page_with_fallback(page, "networkidle", timeout=10000)
                            select_item_invoked = False  # Reset so we can try again
                    except Exception as e:
                        print(f"Error during cart verification: {e}")
                
                elif "FINISHED" in decision:
                    # Before concluding, verify we have actually added items to cart
                    if not on_cart_page:
                        print("Supervisor believes goal is achieved, but let's verify by checking the cart...")
                        continue  # Continue to next iteration, which will trigger cart verification above
                    else:
                        # We're already on the cart page, so check if it has mango products
                        cart_page_content = await page.content()
                        if "mango" in cart_page_content.lower() and not "empty" in cart_page_content.lower():
                            print("\n----- GOAL ACHIEVED -----")
                            print("Supervisor confirmed mango products in cart. Goal achieved!")
                            break
                        else:
                            print("⚠️ Supervisor believes goal is achieved, manually verify if the cart is correct.")
                            print("Continuing workflow to try again...")
                            select_item_invoked = False  # Reset so we can try again
                
                # Check if we've accomplished a sub-goal based on URL alone
                if not mango_finder_invoked and ("s?k=mango" in page_url or "mango" in page_url.lower()):
                    print("Search results detected - marking mango finder step as completed.")
                    mango_finder_invoked = True
                
                if not select_item_invoked and "/dp/" in page_url:
                    print("Product page detected - marking item selection step as completed.")
                    select_item_invoked = True
                
                # Ask if the user wants to continue or take manual action
                print("\nContinue to next interaction? Press Enter or type 'exit' to stop:")
                user_input = await asyncio.get_event_loop().run_in_executor(None, input)
                if user_input.lower() == "exit":
                    break
                
                # Reset captcha_just_solved if not acted upon (safety mechanism)
                if captcha_just_solved and interaction_count > 1:
                    captcha_just_solved = False
            
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

async def wait_for_page_with_fallback(page, state="networkidle", timeout=5000):
    """
    More robust page waiting function that falls back to simpler approaches
    if the main approach fails.
    """
    try:
        # Try the requested wait first
        await page.wait_for_load_state(state, timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        print(f"Timeout waiting for '{state}'. Trying fallback wait approaches...")
        
        try:
            # Try waiting for DOMContentLoaded instead
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
            print("Page DOM content loaded")
        except Exception:
            # If that fails too, just wait a fixed time
            print("DOM load timeout. Using fixed delay fallback.")
            
        # Fixed delay as final fallback
        await asyncio.sleep(3)
        return False

if __name__ == "__main__":
    asyncio.run(simple_supervisor())
