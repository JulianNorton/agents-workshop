## Prerequisites 
* Python installed
* Visual Code studio or some other code editor
* OpenAI API key

## Setup Instructions
1. In terminal, create a `.env` file and put in your API key.
    * mac `touch .env`
    * windows `New-Item -Path .env -ItemType File` 
    * It should look like this:
    ```
    openai_api_key="abc123567"
    ```

## Virtual Environment Setup

**On Windows:**
1. Open a terminal.
2. Run: `python -m venv venv` (skip if you already have a .\venv...)
3. Activate it: `.\venv\Scripts\activate`
4. Install dependencies: `pip install -r requirements.txt`

**On macOS/Linux:**
1. Open a terminal.
2. Run: `python3 -m venv venv`
3. Activate it: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`

## Running the Application
1. Ensure your virtual environment is activated.
1. install the browser for Playright (for computer-use assistance) `playwright install`
1. `python .\cua_mangomax.py` 