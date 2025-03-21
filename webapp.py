from flask import Flask, render_template, request
import asyncio
from agents import Agent, Runner

# Simple query agent to call OpenAI
main_agent = Agent(
    name="Simple Query Agent",
    instructions="Processes simple text queries using OpenAI.",
    model="gpt-4o-mini",
    # model="o3-mini",
)

# Placeholder for a second agent: History Tutor
history_tutor_agent = Agent(
    name="History Tutor",
    handoff_description="Specialist agent for historical questions",
    instructions="You provide assistance with historical queries. Explain important events and context clearly.",
)

def call_history_tutor(query: str):
    # Placeholder function for calling the History Tutor agent asynchronously
    result = asyncio.run(Runner.run(history_tutor_agent, query))
    return result.final_output

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    main_result = None
    history_result = None
    if request.method == 'POST':
        user_input = request.form.get('text')
        result = asyncio.run(Runner.run(main_agent, user_input))
        main_result = result.final_output
        history_result = call_history_tutor("Explain the significance of the Battle of Hastings.")
    return render_template('index.html', main_result=main_result, history_result=history_result)

if __name__ == '__main__':
    app.run(debug=True)