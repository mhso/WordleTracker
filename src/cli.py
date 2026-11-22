from argparse import ArgumentParser
from asyncio import iscoroutinefunction
import asyncio

from wordle_tracker.database import DatabaseClient
from wordle_tracker.extract_score import extract_wordle_scores
from wordle_tracker import messages

from dotenv import load_dotenv


class ScriptRunner:
    def extract_score(self, test_image: str):
        avatars = [
            (115142485579137029, "../test_data/avatar_dave.png"),
            (172757468814770176, "../test_data/avatar_murt.png"),
            (267401734513491969, "../test_data/avatar_gual.png"),
            (331082926475182081, "../test_data/avatar_muds.png"),
            (347489125877809155, "../test_data/avatar_no.png"),
        ]

        scores = extract_wordle_scores(f"../test_data/{test_image}.png", avatars)
        print(scores)

    def cursor_func(self, func: str, *args):
        with DatabaseClient(False) as cursor:
            print(getattr(cursor, func)(*args))

    def discord_messages(self, func: str, *args):
        print(getattr(messages, func)(DatabaseClient(False), *args))

if __name__ == "__main__":
    load_dotenv()

    PARSER = ArgumentParser()

    TEST_RUNNER = ScriptRunner()
    FUNCS = [
        func
        for func in TEST_RUNNER.__dir__()
        if not func.startswith("_") and callable(getattr(TEST_RUNNER, func))
    ]

    PARSER.add_argument("func", choices=FUNCS)
    PARSER.add_argument("args", nargs="*")

    ARGS = PARSER.parse_args()

    func = getattr(TEST_RUNNER, ARGS.func)

    if iscoroutinefunction(func):
        asyncio.run(func(*ARGS.args))
    else:
        func(*ARGS.args)
