import asyncio
from simple_supervisor import simple_supervisor

async def main():
    """
    Main function that runs the simplified supervisor agent.
    """
    print("Starting simplified supervisor agent...")
    await simple_supervisor()
    print("Supervisor completed.")

if __name__ == "__main__":
    asyncio.run(main())
