Computer use
Build a computer-using agent that can perform tasks on your behalf.
Overview
Computer use is a practical application of our Computer-Using Agent (CUA) model, computer-use-preview, which combines the vision capabilities of GPT-4o with advanced reasoning to simulate controlling computer interfaces and performing tasks.

Computer use is available through the Responses API. It is not available on Chat Completions.

Computer use is in beta. Because the model is still in preview and may be susceptible to exploits and inadvertent mistakes, we discourage trusting it in fully authenticated environments or for high-stakes tasks. See limitations and risk and safety best practices below. You must use the Computer Use tool in line with OpenAI's Usage Policy and Business Terms.

How it works
The computer use tool operates in a continuous loop. It sends computer actions, like click(x,y) or type(text), which your code executes on a computer or browser environment and then returns screenshots of the outcomes back to the model.

In this way, your code simulates the actions of a human using a computer interface, while our model uses the screenshots to understand the state of the environment and suggest next actions.

This loop lets you automate many tasks requiring clicking, typing, scrolling, and more. For example, booking a flight, searching for a product, or filling out a form.

Refer to the integration section below for more details on how to integrate the computer use tool, or check out our sample app repository to set up an environment and try example integrations.

CUA sample app
Examples of how to integrate the computer use tool in different environments

Setting up your environment
Before integrating the tool, prepare an environment that can capture screenshots and execute the recommended actions. We recommend using a sandboxed environment for safety reasons.

In this guide, we'll show you examples using either a local browsing environment or a local virtual machine, but there are more example computer environments in our sample app.

Set up a local browsing environment
Set up a local virtual machine
Integrating the CUA loop
These are the high-level steps you need to follow to integrate the computer use tool in your application:

Send a request to the model: Include the computer tool as part of the available tools, specifying the display size and environment. You can also include in the first request a screenshot of the initial state of the environment.

Receive a response from the model: Check if the response has any computer_call items. This tool call contains a suggested action to take to progress towards the specified goal. These actions could be clicking at a given position, typing in text, scrolling, or even waiting.

Execute the requested action: Execute through code the corresponding action on your computer or browser environment.

Capture the updated state: After executing the action, capture the updated state of the environment as a screenshot.

Repeat: Send a new request with the updated state as a computer_call_output, and repeat this loop until the model stops requesting actions or you decide to stop.

Computer use diagram

1. Send a request to the model
Send a request to create a Response with the computer-use-preview model equipped with the computer_use_preview tool. This request should include details about your environment, along with an initial input prompt.

If you want to show a summary of the reasoning performed by the model, you can include the generate_summary parameter in the request. This can be helpful if you want to debug or show what's happening behind the scenes in your interface. The summary can either be concise or detailed.

Optionally, you can include a screenshot of the initial state of the environment.

To be able to use the computer_use_preview tool, you need to set the truncation parameter to "auto" (by default, truncation is disabled).

Send a CUA request
from openai import OpenAI
client = OpenAI()

response = client.responses.create(
    model="computer-use-preview",
    tools=[{
        "type": "computer_use_preview",
        "display_width": 1024,
        "display_height": 768,
        "environment": "browser" # other possible values: "mac", "windows", "ubuntu"
    }],
    input=[
        {
            "role": "user",
            "content": "Check the latest OpenAI news on bing.com."
        }
        # Optional: include a screenshot of the initial state of the environment
        # {
        #     type: "input_image",
        #     image_url: f"data:image/png;base64,{screenshot_base64}"
        # }
    ],
    reasoning={
        "generate_summary": "concise",
    },
    truncation="auto"
)

print(response.output)
2. Receive a suggested action
The model returns an output that contains either a computer_call item, just text, or other tool calls, depending on the state of the conversation.

Examples of computer_call items are a click, a scroll, a key press, or any other event defined in the API reference. In our example, the item is a click action:

CUA suggested action
"output": [
    {
        "type": "reasoning",
        "id": "rs_67cc...",
        "summary": [
            {
                "type": "summary_text",
                "text": "Clicking on the browser address bar."
            }
        ]
    },
    {
        "type": "computer_call",
        "id": "cu_67cc...",
        "call_id": "call_zw3...",
        "action": {
            "type": "click",
            "button": "left",
            "x": 156,
            "y": 50
        },
        "pending_safety_checks": [],
        "status": "completed"
    }
]
Reasoning items
The model may return a reasoning item in the response output for some actions. If you don't use the previous_response_id parameter as shown in Step 5 and manage the inputs array on your end, make sure to include those reasoning items along with the computer calls when sending the next request to the CUA model–or the request will fail.

The reasoning items are only compatible with the same model that produced them (in this case, computer-use-preview). If you implement a flow where you use several models with the same conversation history, you should filter these reasoning items out of the inputs array you send to other models.

Safety checks
The model may return safety checks with the pending_safety_check parameter. Refer to the section on how to acknowledge safety checks below for more details.

3. Execute the action in your environment
Execute the corresponding actions on your computer or browser. How you map a computer call to actions through code depends on your environment. This code shows example implementations for the most common computer actions.


Playwright

Docker
Execute the action
def handle_model_action(page, action):
    """
    Given a computer action (e.g., click, double_click, scroll, etc.),
    execute the corresponding operation on the Playwright page.
    """
    action_type = action.type
    
    try:
        match action_type:

            case "click":
                x, y = action.x, action.y
                button = action.button
                print(f"Action: click at ({x}, {y}) with button '{button}'")
                # Not handling things like middle click, etc.
                if button != "left" and button != "right":
                    button = "left"
                page.mouse.click(x, y, button=button)

            case "scroll":
                x, y = action.x, action.y
                scroll_x, scroll_y = action.scroll_x, action.scroll_y
                print(f"Action: scroll at ({x}, {y}) with offsets (scroll_x={scroll_x}, scroll_y={scroll_y})")
                page.mouse.move(x, y)
                page.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")

            case "keypress":
                keys = action.keys
                for k in keys:
                    print(f"Action: keypress '{k}'")
                    # A simple mapping for common keys; expand as needed.
                    if k.lower() == "enter":
                        page.keyboard.press("Enter")
                    elif k.lower() == "space":
                        page.keyboard.press(" ")
                    else:
                        page.keyboard.press(k)
            
            case "type":
                text = action.text
                print(f"Action: type text: {text}")
                page.keyboard.type(text)
            
            case "wait":
                print(f"Action: wait")
                time.sleep(2)

            case "screenshot":
                # Nothing to do as screenshot is taken at each turn
                print(f"Action: screenshot")

            # Handle other actions here

            case _:
                print(f"Unrecognized action: {action}")

    except Exception as e:
        print(f"Error handling action {action}: {e}")
4. Capture the updated screenshot
After executing the action, capture the updated state of the environment as a screenshot, which also differs depending on your environment.


Playwright

Docker
Capture and send the updated screenshot
def get_screenshot(page):
    """
    Take a full-page screenshot using Playwright and return the image bytes.
    """
    return page.screenshot()
5. Repeat
Once you have the screenshot, you can send it back to the model as a computer_call_output to get the next action. Repeat these steps as long as you get a computer_call item in the response.

Repeat steps in a loop
import time
import base64
from openai import OpenAI
client = OpenAI()

def computer_use_loop(instance, response):
    """
    Run the loop that executes computer actions until no 'computer_call' is found.
    """
    while True:
        computer_calls = [item for item in response.output if item.type == "computer_call"]
        if not computer_calls:
            print("No computer call found. Output from model:")
            for item in response.output:
                print(item)
            break  # Exit when no computer calls are issued.

        # We expect at most one computer call per response.
        computer_call = computer_calls[0]
        last_call_id = computer_call.call_id
        action = computer_call.action

        # Execute the action (function defined in step 3)
        handle_model_action(instance, action)
        time.sleep(1)  # Allow time for changes to take effect.

        # Take a screenshot after the action (function defined in step 4)
        screenshot_bytes = get_screenshot(instance)
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        # Send the screenshot back as a computer_call_output
        response = client.responses.create(
            model="computer-use-preview",
            previous_response_id=response.id,
            tools=[
                {
                    "type": "computer_use_preview",
                    "display_width": 1024,
                    "display_height": 768,
                    "environment": "browser"
                }
            ],
            input=[
                {
                    "call_id": last_call_id,
                    "type": "computer_call_output",
                    "output": {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{screenshot_base64}"
                    }
                }
            ],
            truncation="auto"
        )

    return response
Handling conversation history
You can use the previous_response_id parameter to link the current request to the previous response. We recommend using this method if you don't want to manage the conversation history on your side.

If you do not want to use this parameter, you should make sure to include in your inputs array all the items returned in the response output of the previous request, including reasoning items if present.

Acknowledge safety checks
We have implemented safety checks in the API to help protect against prompt injection and model mistakes. These checks include:

Malicious instruction detection: we evaluate the screenshot image and check if it contains adversarial content that may change the model's behavior.
Irrelevant domain detection: we evaluate the current_url (if provided) and check if the current domain is considered relevant given the conversation history.
Sensitive domain detection: we check the current_url (if provided) and raise a warning when we detect the user is on a sensitive domain.
If one or multiple of the above checks is triggered, a safety check is raised when the model returns the next computer_call, with the pending_safety_checks parameter.

Pending safety checks
"output": [
    {
        "type": "reasoning",
        "id": "rs_67cb...",
        "summary": [
            {
                "type": "summary_text",
                "text": "Exploring 'File' menu option."
            }
        ]
    },
    {
        "type": "computer_call",
        "id": "cu_67cb...",
        "call_id": "call_nEJ...",
        "action": {
            "type": "click",
            "button": "left",
            "x": 135,
            "y": 193
        },
        "pending_safety_checks": [
            {
                "id": "cu_sc_67cb...",
                "code": "malicious_instructions",
                "message": "We've detected instructions that may cause your application to perform malicious or unauthorized actions. Please acknowledge this warning if you'd like to proceed."
            }
        ],
        "status": "completed"
    }
]
You need to pass the safety checks back as acknowledged_safety_checks in the next request in order to proceed. In all cases where pending_safety_checks are returned, actions should be handed over to the end user to confirm model behavior and accuracy.

malicious_instructions and irrelevant_domain: end users should review model actions and confirm that the model is behaving as intended.
sensitive_domain: ensure an end user is actively monitoring the model actions on these sites. Exact implementation of this "watch mode" may vary by application, but a potential example could be collecting user impression data on the site to make sure there is active end user engagement with the application.
Acknowledge safety checks
from openai import OpenAI
client = OpenAI()

response = client.responses.create(
    model="computer-use-preview",
    previous_response_id="<previous_response_id>",
    tools=[{
        "type": "computer_use_preview",
        "display_width": 1024,
        "display_height": 768,
        "environment": "browser"
    }],
    input=[
        {
            "type": "computer_call_output",
            "call_id": "<call_id>",
            "acknowledged_safety_checks": [
                {
                    "id": "<safety_check_id>",
                    "code": "malicious_instructions",
                    "message": "We've detected instructions that may cause your application to perform malicious or unauthorized actions. Please acknowledge this warning if you'd like to proceed."
                }
            ],
            "output": {
                "type": "computer_screenshot",
                "image_url": "<image_url>"
            }
        }
    ],
    truncation="auto"
)
Final code
Putting it all together, the final code should include:

The initialization of the environment
A first request to the model with the computer tool
A loop that executes the suggested action in your environment
A way to acknowledge safety checks and give end users a chance to confirm actions