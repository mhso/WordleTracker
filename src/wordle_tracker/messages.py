from datetime import date

from wordle_tracker.database import DatabaseClient

def get_player_summary_msg(database: DatabaseClient, disc_id: int):
    disc_id = int(disc_id)
    message = f"Wordle summary for **[user:{disc_id}]**:\n"

    with database as cursor:
        times_played = cursor.get_times_played(disc_id)
        times_unfinished = cursor.get_times_unfinished(disc_id)
        times_lost = cursor.get_times_lost(disc_id)
        score_distribution = {
            score: count
            for score, count in cursor.get_player_score_distribution(disc_id)
            if score not in (None, 7)
        }
        for num in range(1, 7):
            if num not in score_distribution:
                score_distribution[num] = 0

        fake_words = len(cursor.get_fake_word_reports(disc_id))
        score_distribution = sorted(score_distribution.items(), key=lambda t: t[0])

        rank, average_score = cursor.get_ranking(disc_id)

        message = (
            f"Days played: **{times_played}**\n"
            f"Days lost: **{times_lost}**\n"
            f"Days given up: **{times_unfinished}**\n"
            f"Words reported as fake: **{fake_words}**\n"
            f"Average score: **{average_score:.2f}**\n"
            f"Ranking: **{rank}**\n\n"
            f"Score Distribution:"
        )

        for score, count in score_distribution:
            message += f"\n- {score}: {count} times"

    return message

def get_ranking_msg(database: DatabaseClient):
    message = "Rankings for Wordle:"

    with database as cursor:
        rankings = cursor.get_ranking()
        for disc_id, rank, score in rankings:
            message += f"\n{rank}: **[user:{disc_id}]** (avg. score: {score:.2f})"

    return message

def get_word_msg(database: DatabaseClient, word_date: str):
    word_date = date(*tuple(map(int, word_date.split("-"))))

    with database as cursor:
        result = cursor.get_word_info(word_date)
        if result is None or result[0] is None:
            return "Can't find the word for that date."

        word, fake_reports, average_score = result

        message = (
            f"The word on {word_date.strftime('%Y-%m-%d')} was **{word.upper()}**\n"
            f"The average score was **{average_score:.2f}**"
        )
        if fake_reports:
            message += f"\nThe word was reported as fake **{fake_reports}** times"

        return message

def get_status_msg(database: DatabaseClient):
    with database as cursor:
        first_date = cursor.get_first_word_date()
        days_tracked = cursor.get_days_tracked()

        message = (
            f"Since **{first_date.strftime('%Y-%m-%d')}** we have played Wordle **{days_tracked}** times\n"

        )
