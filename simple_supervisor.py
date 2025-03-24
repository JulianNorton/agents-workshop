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
            await wait_for_page_with_fallback(page, "networkidle", timeout=30000)
            
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
                    await wait_for_page_with_fallback(page, "networkidle", timeout=30000)
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
                        await wait_for_page_with_fallback(page, "networkidle", timeout=30000)
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
                
                # Rest of the logic (decision making, etc.)
                # ...existing code...
                
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

async def wait_for_page_with_fallback(page, state="networkidle", timeout=30000):
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
