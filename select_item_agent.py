import asyncio
import base64
import json
from typing import Dict, Any, List
from playwright.async_api import Page, TimeoutError
from openai import OpenAI

async def select_item_agent(page: Page) -> Dict[str, Any]:
    """
    Agent responsible for:
    1. Selecting a dried, sugared mango product from the Amazon search results
    2. Navigating to the product detail page
    3. Adding the product to the cart
    """
    client = OpenAI()
    
    # Initialize status tracking
    cart_added = False
    product_selected = False
    
    # Take initial screenshot to start the CUA loop
    screenshot_bytes = await page.screenshot(full_page=True)
    screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    # First, try manual approach (more reliable)
    print("Starting mango product selection process...")
    try:
        # Try direct manual selection first (most reliable)
        result = await manual_select_and_add_to_cart(page)
        if result["status"] == "complete":
            return result
        
        # If manual selection failed or was only partial, try CUA as fallback
        print("Manual selection didn't complete. Trying computer vision approach...")
        
        # Initial request to the CUA model with CORRECT format according to documentation
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
                    "content": "Find a good dried mango product on this Amazon search page, click on it to go to the product page, and then add it to your cart."
                },
                {
                    "type": "input_image",  # FIXED: Changed from "computer_screenshot" to "input_image"
                    "image_url": f"data:image/png;base64,{screenshot_base64}"
                }
            ],
            reasoning={"generate_summary": "concise"},
            truncation="auto"
        )
    except Exception as e:
        print(f"Error initializing CUA for product selection: {e}")
        print("Falling back to pure manual selection...")
        return await manual_select_and_add_to_cart(page)

    # Start the CUA loop
    completed = False
    max_iterations = 15
    iteration = 0
    
    while not completed and iteration < max_iterations:
        iteration += 1
        print(f"CUA Loop Iteration: {iteration}")
        
        # Process any reasoning
        for item in response.output:
            if item.type == "reasoning" and hasattr(item, "summary"):
                for summary in item.summary:
                    if hasattr(summary, "text"):
                        print(f"CUA reasoning: {summary.text}")
        
        # Find computer call actions
        computer_calls = [item for item in response.output if item.type == "computer_call"]
        if not computer_calls:
            print("No computer actions found. CUA workflow complete.")
            completed = True
            break
        
        # Process the computer call
        computer_call = computer_calls[0]
        action = computer_call.action
        call_id = computer_call.call_id
        
        # Handle safety checks if present
        pending_safety_checks = []
        if hasattr(computer_call, "pending_safety_checks") and computer_call.pending_safety_checks:
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
                await asyncio.sleep(2)
                
            # Give the page a moment to update
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Error executing action: {e}")
        
        # Wait for page to stabilize
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            await asyncio.sleep(2)
        
        # Track progress in the workflow
        if not product_selected and "/dp/" in page.url:
            print("✅ Successfully navigated to product detail page")
            product_selected = True
            
            # If we're on product page for 3+ iterations, help with add to cart
            if iteration >= 3:
                add_success = await click_add_to_cart_button(page)
                if add_success:
                    cart_added = True
                    print("✅ Manually added product to cart")
        
        # Check for cart add success
        current_content = await page.content()
        if not cart_added and await is_added_to_cart(page, current_content):
            print("✅ Product successfully added to cart!")
            cart_added = True
        
        # Take a new screenshot
        screenshot_bytes = await page.screenshot(full_page=True)
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        
        # Build the next input with correct format
        next_input = [{
            "call_id": call_id,
            "type": "computer_call_output",
            "output": {
                "type": "input_image",  # FIXED: Changed from "computer_screenshot" to "input_image"
                "image_url": f"data:image/png;base64,{screenshot_base64}"
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
            # If CUA fails, fall back to manual process
            if not (product_selected and cart_added):
                return await manual_select_and_add_to_cart(page)
        
        # If we've been on product page for a while without adding to cart
        if product_selected and not cart_added and iteration > 5:
            print("Product selected but struggling to add to cart. Trying manual intervention...")
            cart_added = await click_add_to_cart_button(page)
            if cart_added:
                print("✅ Manually added product to cart")
                break
    
    # Even if CUA didn't fully succeed, try manual completion as final fallback
    if not (product_selected and cart_added):
        if product_selected and not cart_added:
            # If we're on product page but haven't added to cart
            cart_added = await click_add_to_cart_button(page)
        else:
            # If we haven't even selected a product
            manual_result = await manual_select_and_add_to_cart(page)
            product_selected = manual_result["product_page"]
            cart_added = manual_result["cart_added"]
    
    # Verify cart contents as a final step
    if cart_added:
        try:
            print("Navigating to cart to verify...")
            await page.goto("https://www.amazon.com/gp/cart/view.html")
            await asyncio.sleep(2)
            
            cart_content = await page.content()
            if "mango" in cart_content.lower() and not "empty" in cart_content.lower():
                print("✅ Confirmed mango product in cart!")
                cart_added = True
            else:
                print("⚠️ Cart verification failed - no mangos found in cart")
                cart_added = False
        except Exception as e:
            print(f"Error verifying cart: {e}")
    
    # Return the final status
    return {
        "url": page.url,
        "status": "complete" if (product_selected and cart_added) else 
                 "partial" if product_selected else "incomplete",
        "product_page": product_selected,
        "cart_added": cart_added,
        "iterations": iteration
    }

async def manual_select_and_add_to_cart(page: Page) -> Dict[str, Any]:
    """
    Manually selects a mango product and adds it to cart.
    This is a fallback when CUA fails.
    """
    product_selected = False
    cart_added = False
    
    try:
        # Step 1: Try to find and click on a mango product
        if "/dp/" not in page.url:
            print("Looking for a mango product to click...")
            product_links = []
            
            # Try different ways to find product links
            try:
                # Method 1: Look for links containing product images
                links = await page.query_selector_all("a.a-link-normal.s-no-outline")
                if links:
                    product_links.extend(links)
                
                # Method 2: Look for div elements that contain product info
                product_divs = await page.query_selector_all("div[data-asin]:not([data-asin=''])") 
                for div in product_divs:
                    link = await div.query_selector("a")
                    if link:
                        product_links.append(link)
                
                # If we found products, click the first one
                if product_links:
                    print(f"Found {len(product_links)} potential products. Clicking first one...")
                    await product_links[0].click()
                    await asyncio.sleep(3)
                    
                    # Check if we navigated to a product page
                    if "/dp/" in page.url:
                        product_selected = True
                        print("✅ Successfully navigated to product page")
                    else:
                        print("⚠️ Clicked but didn't navigate to a product page")
                else:
                    # Desperate approach: look for any link with "mango" in the text
                    mango_links = await page.query_selector_all("a:has-text('mango')")
                    if mango_links:
                        print("Found links with 'mango' text. Clicking first one...")
                        await mango_links[0].click()
                        await asyncio.sleep(3)
                        if "/dp/" in page.url:
                            product_selected = True
                            print("✅ Successfully navigated to product page (via text search)")
            except Exception as e:
                print(f"Error selecting product: {e}")
        else:
            # We're already on a product page
            product_selected = True
            print("Already on a product page")
        
        # Step 2: If we're on a product page, try to add to cart
        if product_selected or "/dp/" in page.url:
            product_selected = True
            cart_added = await click_add_to_cart_button(page)
            
            if cart_added:
                print("✅ Successfully added product to cart")
            else:
                print("❌ Failed to add product to cart")
        
        return {
            "url": page.url,
            "status": "complete" if (product_selected and cart_added) else 
                     "partial" if product_selected else "incomplete",
            "product_page": product_selected,
            "cart_added": cart_added
        }
    except Exception as e:
        print(f"Error in manual selection process: {e}")
        return {
            "url": page.url,
            "status": "error",
            "error": str(e),
            "product_page": product_selected,
            "cart_added": cart_added
        }

async def click_add_to_cart_button(page: Page) -> bool:
    """
    Tries multiple strategies to click the Add to Cart button on a product page.
    Returns True if successful.
    """
    print("Attempting to click Add to Cart button...")
    
    # Strategy 1: Try the exact selector we know works on Amazon
    selectors = [
        "button[name='submit.addToCart'][aria-label='Add to cart']", 
        "button#a-autoid-1-announce",
        "button#a-autoid-2-announce",
        "#add-to-cart-button",
        "input#add-to-cart-button", 
        "input[name='submit.addToCart']",
        "span#submit\\.add-to-cart-announce",
        "span#submit\\.add-to-cart"
    ]
    
    for selector in selectors:
        try:
            print(f"Trying selector: {selector}")
            button = await page.query_selector(selector)
            if button:
                await button.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                await button.click()
                await asyncio.sleep(3)
                
                # Check if successfully added to cart
                content = await page.content()
                if await is_added_to_cart(page, content):
                    return True
        except Exception as e:
            print(f"Error with selector {selector}: {e}")
    
    # Strategy 2: Try finding by text "Add to Cart"
    try:
        add_text_elements = await page.query_selector_all("text='Add to Cart'")
        if add_text_elements:
            for element in add_text_elements:
                try:
                    await element.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    await element.click()
                    await asyncio.sleep(3)
                    
                    content = await page.content()
                    if await is_added_to_cart(page, content):
                        return True
                except Exception:
                    continue
    except Exception as e:
        print(f"Error with text search: {e}")
    
    # Strategy 3: Try JavaScript approach as a last resort
    try:
        print("Trying JavaScript approach...")
        script = """
        // Try to find and click add to cart button
        function findAndClickAddToCart() {
            // All possible selectors
            const selectors = [
                'button[name="submit.addToCart"][aria-label="Add to cart"]',
                'button#a-autoid-1-announce',
                'button#a-autoid-2-announce',
                '#add-to-cart-button',
                'input#add-to-cart-button',
                'input[name="submit.addToCart"]',
                'span#submit\\.add-to-cart-announce',
                'span#submit\\.add-to-cart'
            ];
            
            // Try each selector
            for (const selector of selectors) {
                const element = document.querySelector(selector);
                if (element) {
                    element.click();
                    console.log("Clicked:", selector);
                    return true;
                }
            }
            
            // Try finding by text content
            const allButtons = document.querySelectorAll('button, input[type="submit"], span[role="button"]');
            for (const button of allButtons) {
                if (button.textContent && button.textContent.includes('Add to Cart')) {
                    button.click();
                    console.log("Clicked by text content");
                    return true;
                }
            }
            
            return false;
        }
        
        return findAndClickAddToCart();
        """
        
        result = await page.evaluate(script)
        await asyncio.sleep(3)
        
        content = await page.content()
        if result or await is_added_to_cart(page, content):
            return True
    except Exception as e:
        print(f"JavaScript approach failed: {e}")
    
    return False

async def is_added_to_cart(page: Page, content: str = None) -> bool:
    """
    Checks if an item was successfully added to the cart.
    """
    if content is None:
        content = await page.content()
    
    # Check for success indicators in the page content
    success_indicators = [
        "Added to Cart",
        "added to cart",
        "added to Cart",
        "Cart subtotal",
        "Proceed to checkout",
        "proceed to checkout",
        "Cart updated",
        "huc-v2-order-row-confirm-text"
    ]
    
    for indicator in success_indicators:
        if indicator.lower() in content.lower():
            return True
    
    # Check for cart count increase
    try:
        cart_count_element = await page.query_selector("#nav-cart-count")
        if cart_count_element:
            count_text = await cart_count_element.text_content()
            if count_text and int(count_text.strip()) > 0:
                return True
    except Exception:
        pass
    
    return False