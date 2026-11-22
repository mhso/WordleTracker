import asyncio
import re
from datetime import date, datetime
from time import time
from os import environ

from discord import Client, Guild, Intents, Forbidden, Interaction, Member, Message, RawMessageUpdateEvent, TextChannel
from discord.interactions import Interaction
from discord import app_commands
from loguru import logger
from httpx import AsyncClient
from dateutil.relativedelta import relativedelta

from wordle_tracker.database import DatabaseClient, DatabaseCursor
from wordle_tracker.models import Environment, Day, Score
from wordle_tracker import messages
from wordle_tracker.extract_score import extract_wordle_scores

CORE_GUILD_ID = 803987403932172359
MY_GUILD_ID = 512363920044982272
MAIN_CHANNEL_ID = 803987404733808662
TEST_CHANNEL_ID = 512363920044982274
WORDLE_BOT_ID = 1211781489931452447

USER_TEMPLATE_PATTERN = re.compile(r"\[user\:(\d+)\]")

class DiscordClient(Client):
    def __init__(self, database_client: DatabaseClient, environment: Environment):
        super().__init__(
            intents=Intents(
                members=True,
                guilds=True,
                guild_messages=True,
                message_content=True,
            )
        )

        self.guild_id = CORE_GUILD_ID if environment is Environment.PRODUCTION else MY_GUILD_ID
        self.channel_id = MAIN_CHANNEL_ID if environment is Environment.PRODUCTION else TEST_CHANNEL_ID

        with database_client as cursor:
            latest_entry = cursor.get_latest_score_entry()

        if latest_entry:
            self.latest_id, d = latest_entry
            self.latest_timestamp = datetime(d.year, d.month, d.day)
        else:
            self.latest_id = None
            self.latest_timestamp = datetime(2025, 9, 13)

        print("Latest message: ", self.latest_id, self.latest_timestamp)

        self.database_client = database_client
        self.environment = environment
        self.httpx_client = AsyncClient()

        # Discord guild and channel
        self.guild: Guild | None = None
        self.channel: TextChannel | None = None

        # Avatars
        self._avatar_cache: dict[int, tuple[float, str]] = {}
        self._avatar_ttl = 6 * 60 * 60
        self._avatar_cache_size = 10

        self._initialized = False

    async def on_ready(self):
        if self._initialized:
            return

        self.guild = self.get_guild(self.guild_id)
        self.channel = self.guild.get_channel(self.channel_id)

        try:
            await self.sync_messages()
        except Exception:
            logger.exception("Exception when syncing Discord messages!")

        self._initialized = True

    async def on_connect(self):
        logger.info("Discord client connected")

    async def on_disconnect(self):
        logger.info("Discord client disconnected...")

    async def get_avatar(self, disc_id: int):
        if self.guild is None:
            return None

        member = self.guild.get_member(disc_id)
        if member is None or member.avatar is None:
            return None

        if disc_id in self._avatar_cache:
            timestamp, path = self._avatar_cache[disc_id]

            if time() > timestamp + self._avatar_ttl or len(self._avatar_cache) > self._avatar_cache_size:
                del self._avatar_cache[disc_id]

            else:
                return path

        path = f"{environ['RESOURCES_PATH']}/avatars/{disc_id}.png"

        with open(path, "wb") as fp:
            await member.avatar.save(fp)

        self._avatar_cache[disc_id] = (time(), path)

        return path

    def _get_members(self):
        return [member for member in self.guild.members if not member.bot]

    async def _get_word_info(self, date: date):
        date_fmt = date.strftime("%Y-%m-%d")
        response = await self.httpx_client.get(f"https://www.nytimes.com/svc/wordle/v2/{date_fmt}.json")
        if response.status_code != 200:
            logger.error(f"Getting Wordle word for {date_fmt} returned status {response.status_code}")
            return None, None

        json_data = response.json()

        return (json_data["solution"], json_data["days_since_launch"])

    async def _save_scores(
        self,
        message: Message,
        scores: list[tuple[int, int]],
        cursor: DatabaseCursor,
        live: bool,
    ):
        score_models = []
        for disc_id, score in scores:
            date = message.created_at if live else message.created_at + relativedelta(days=-1)
            date = date.date()
            day_model = cursor.get_day_entry(date)

            if day_model is None:
                word, day = await self._get_word_info(date)

                day_model = Day(word=word, day=day, date=date)
                cursor.session.add(day_model)
                cursor.session.flush()

            score_model = day_model.get_score_entry(disc_id)

            if score_model is None:
                date_finished = message.created_at if score is not None else None

                score_model = Score(
                    day_id=day_model.id,
                    disc_id=disc_id,
                    score=score,
                    message_id=message.id,
                    date_started=message.edited_at or message.created_at,
                    date_finished=date_finished,
                )
                cursor.session.add(score_model)
            else:
                score_model.score = score

                if score is not None:
                    score_model.date_finished = datetime.now()

            score_models.append(score_model)

        return score_models

    async def _find_user(self, name: str):
        for member in self._get_members():
            for attribute in (member.global_name, member.nick, member.display_name, member.name):
                if attribute is not None:
                    if attribute.lower() == name.lower():
                        return member.id

        return None

    def _parse_wordle_players(self, content: str):
        single_keyword = "was playing"
        multi_keyword = "were playing"

        if content.endswith(single_keyword):
            # A single person playing Wordle
            player_names = [content.removesuffix(single_keyword)]
        elif content.endswith(multi_keyword):
            # Multiple people playing Wordle
            player_names = [content.removesuffix(multi_keyword)]
        else:
            player_names = []

        return [self._find_user(name) for name in player_names]

    async def _handle_wordle_message(self, message: Message):
        """
        Handle a message from the official Discord Wordle bot.
        """
        user_avatars = [(member.id, await self.get_avatar(member.id)) for member in self._get_members()]

        image_bytes = await message.attachments[0].read()
        return extract_wordle_scores(image_bytes, user_avatars)

    def _is_valid_wordle_message(self, message: Message):
        if message.channel.id != self.channel.id or message.author.id != WORDLE_BOT_ID:
            return False

        if message.attachments == [] or not message.attachments[0].content_type.startswith("image/"):
            return False

        return True

    async def _on_sync_complete(self, message: Message):
        self.latest_timestamp = message.created_at
        self.latest_id = message.id

    async def on_message(self, message: Message):
        if message.author.id != WORDLE_BOT_ID or message.channel.guild != self.guild:
            return

        if not self._is_valid_wordle_message(message):
            return

        score_entries = await self._handle_wordle_message(message)
        if score_entries == []:
            return

        live = not message.content.startswith("**Your group")

        with self.database_client as cursor:
            await self._save_scores(message, score_entries, cursor, live)
            await self._on_sync_complete(message)

    async def on_message_edit(self, message_before: Message | None, message_after: Message):
        logger.info("Message was edited!")
        if message_after.author.id != WORDLE_BOT_ID:
            return

        await self._handle_wordle_message(message_after, True)

    async def on_raw_message_edit(self, payload: RawMessageUpdateEvent):
        if payload.cached_message is not None:
            return

        await self.on_message_edit(None, payload.message)

    async def sync_messages(self):
        try:
            logger.info("Starting message sync...")

            num_entries = 0
            latest_message = None
            with self.database_client as cursor:
                async for message in self.channel.history(limit=None, after=self.latest_timestamp, oldest_first=True):
                    if message.id == self.latest_id or not self._is_valid_wordle_message(message):
                        continue

                    live = not message.content.startswith("**Your group")

                    scores = await self._handle_wordle_message(message)
                    if scores == []:
                        continue

                    await asyncio.sleep(1)

                    score_models = await self._save_scores(message, scores, cursor, live)
                    num_entries += len(score_models)

                    yesterday = message.created_at + relativedelta(days=-1)

                    print(f"Saving {len(score_models)} scores for {yesterday.strftime('%Y-%m-%d')}")

                    latest_message = message

                if latest_message is not None:
                    self.latest_timestamp = latest_message.created_at
                    self.latest_id = latest_message.id

                logger.info(f"Found {num_entries} new Wordle entries")

        except Forbidden:
            logger.exception("Insufficient permissions to read Discord messages!")

    def _replace_user_ids(self, message: str):
        members = {member.id: member for member in self._get_members()}

        for full, disc_id in re.findall(USER_TEMPLATE_PATTERN, message):
            member = members.get(disc_id)
            name = member.display_name if member is not None else "Unknown"
            message = message.replace(full, name)

        return message

    @app_commands.command(description="Show a summary of your Wordle performance.")
    async def summary(self, interaction: Interaction, member: Member):
        response_msg = messages.get_player_summary_msg(self.database_client, member.id)
        await interaction.response.send_message(self._replace_user_ids(response_msg))

    @app_commands.command(description="Show a general overview of Wordle stats in the server.")
    async def status(self, interaction: Interaction):
        response_msg = messages.get_status_msg(self.database_client)
        await interaction.response.send_message(response_msg)

    @app_commands.command(description="Show the ranking of players by average Wordle score.")
    async def ranking(self, interaction: Interaction):
        response_msg = messages.get_ranking_msg(self.database_client)
        await interaction.response.send_message(self._replace_user_ids(response_msg))

    @app_commands.command(description="Show information about a word on a given date, fx. '2026-11-11'")
    async def word(self, interaction: Interaction, date: str):
        response_msg = messages.get_word_msg(self.database_client, date)
        await interaction.response.send_message(self._replace_user_ids(response_msg))
