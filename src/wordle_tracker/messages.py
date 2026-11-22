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
            if score not in (8, 7)
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
            message += f"\n- **{score}**: {count} times"

    return message

def get_status_msg(database: DatabaseClient):
    with database as cursor:
        first_date = cursor.get_first_word_date()
        days_tracked = cursor.get_days_tracked()
        best_word, best_day, best_score = cursor.get_lowest_average_score()
        worst_word, worst_day, worst_score = cursor.get_highest_average_score()

        return (
            f"Since **{first_date.strftime('%Y-%m-%d')}** we have played Wordle **{days_tracked}** times\n"
            f"Our lowest average scores was **{best_score}** on {best_day} with the word **{best_word.upper()}**\n"
            f"Our highest average scores was **{worst_score}** on {worst_day} with the word **{worst_word.upper()}**"
        )

def get_ranking_msg(database: DatabaseClient):
    message = "Rankings for Wordle:"

    rank_emojis = ["🥇", "🥈", "🥉", "🫠", "💩"]

    with database as cursor:
        rankings = cursor.get_ranking()
        for disc_id, rank, score in rankings:
            emoji = rank_emojis[rank - 1] if rank - 1 < len(rank_emojis) else f"{rank}"
            message += f"\n{emoji}: **[user:{disc_id}]** (avg. score: {score:.2f})"

    return message

def get_word_msg(database: DatabaseClient, parsed_date: date):
    with database as cursor:
        result = cursor.get_word_info(parsed_date)
        if result is None or result[0] is None:
            return "Can't find the word for that date."

        word, fake_reports, average_score = result

        message = (
            f"The word on {parsed_date.strftime('%Y-%m-%d')} was **{word.upper()}**\n"
            f"The average score was **{average_score:.2f}**"
        )
        if fake_reports:
            message += f"\nThe word was reported as fake **{fake_reports}** times"

        return message
