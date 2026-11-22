from sys import stdout
from os import environ

from dotenv import load_dotenv
from loguru import logger

from wordle_tracker.models import Environment
from wordle_tracker.database import DatabaseClient
from wordle_tracker.discord_bot import DiscordClient, init_commands

def main():
    load_dotenv()

    logger.remove()
    logger.add(stdout, colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> <level>{message}</level>")
    logger.add("../log/log.log", serialize=True, rotation="5 MB")

    environment = Environment(environ["ENVIRONMENT"])
    logger.info(f"Running in +++{environment.name}+++ mode")

    # Create database client
    logger.info("Starting database client...")
    database_client = DatabaseClient()

    # Create and start Discord client
    logger.info("Starting Discord client...")
    discord_client = DiscordClient(database_client, environment)

    # Initialize slash commands
    init_commands(discord_client)

    discord_client.run(environ["DISCORD_TOKEN"])

if __name__ == "__main__":
    main()
