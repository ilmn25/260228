import sys
import asyncio
from system import cli, discord_cli
import inquirer

def main():
    questions = [
        inquirer.List(
            'interface',
            message="Select interface to run:",
            choices=['CLI', 'Discord CLI'],
            carousel=True
        )
    ]
    answer = inquirer.prompt(questions)
    if not answer:
        print("No selection made. Exiting.")
        return
    if answer['interface'] == 'CLI':
        asyncio.run(cli.run_agent())
    else:
        asyncio.run(discord_cli.main())

if __name__ == "__main__":
    main()
