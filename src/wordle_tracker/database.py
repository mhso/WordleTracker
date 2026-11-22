from datetime import date
import os
from shutil import copyfile
from threading import get_ident

from loguru import logger
from sqlalchemy import Engine, text, create_engine, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.functions import (
    min as sqlamin,
    max as sqlamax,
    count,
    sum as sqlasum,
)

from wordle_tracker.models import Base, Day, FakeWord, Score

class DatabaseCursor:
    def __init__(self, engine: Engine):
        self.session = Session(engine)

    def get_latest_score_entry(self):
        stmt = select(Day, sqlamax(Day.date)).select_from(Day).options(selectinload(Day.scores))

        latest = self.session.execute(stmt).one_or_none()
        if latest is None:
            return None

        day, latest_date = latest
        if day is None:
            return None

        if day.scores:
            message_id = max(score.message_id for score in day.scores)
        else:
            message_id = None

        return message_id, latest_date

    def get_day_entry(self, timestamp: date):
        stmt = select(Day).options(
            selectinload(Day.scores)
        ).where(Day.date == timestamp)

        return self.session.execute(stmt).scalar_one_or_none()

    def get_player_average_score(self, disc_id: int | None = None):
        select_items = [sqlasum(Score.score) / count(Score.score)]
        if disc_id is None:
            select_items.append(Score.disc_id)

        stmt = select(*select_items).select_from(Score).where(Score.score > 0)

        if disc_id is None:
            stmt = stmt.group_by(Score.disc_id).order_by(Score.disc_id)
        else:
            stmt = stmt.where(Score.disc_id == disc_id)

        result = self.session.execute(stmt)

        return result.scalar_one_or_none() if disc_id else result.all()

    def get_player_score_distribution(self, disc_id: int):
        stmt = select(Score.score, count("*")).select_from(Score).group_by(Score.score).where(Score.disc_id == disc_id)
        return self.session.execute(stmt).all()

    def _get_specfic_score(self, disc_id: int, score: int | None):
        stmt = select(count("*")).select_from(Score).where(Score.disc_id == disc_id, Score.score == score)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_times_unfinished(self, disc_id: int):
        return self._get_specfic_score(disc_id, 8)

    def get_times_lost(self, disc_id: int):
        return self._get_specfic_score(disc_id, 7)

    def get_times_played(self, disc_id: int):
        stmt = select(count("*")).select_from(Score).where(Score.disc_id == disc_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_ranking(self, disc_id: int | None = None):
        scores = sorted(self.get_player_average_score(), key=lambda r: r[0])
        rankings = []
        for index, (score, user_id) in enumerate(scores, start=1):
            if disc_id and user_id == disc_id:
                return index, score

            rankings.append((user_id, index, score))

        return rankings

    def get_fake_word_reports(self, disc_id: int | None = None):
        stmt = select(Day).join(FakeWord, Day.id == FakeWord.day_id)
        if disc_id:
            stmt = stmt.where(FakeWord.reported_by == disc_id)

        result = self.session.execute(stmt)

        return result.scalars().all()

    def get_word_average_score(self, word_date: date):
        stmt = select(
            sqlasum(Score.score) / count(Score.score)
        ).join(
            Day, Day.id == Score.day_id
        ).where(Day.date == word_date, Score.score != None)

        return self.session.execute(stmt).scalar_one_or_none()

    def get_word_info(self, word_date: date):
        average_score = self.get_word_average_score(word_date)
        stmt = select(
            Day.word, count(FakeWord.reported_by)
        ).join(
            FakeWord, Day.id == FakeWord.day_id, isouter=True
        ).where(Day.date == word_date)

        result = self.session.execute(stmt).one_or_none()
        if not result:
            return None

        word, fake = result

        return word, fake, average_score

    def get_days_tracked(self):
        stmt = select(count("*")).select_from(Day)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_first_word_date(self):
        stmt = select(Day.date).order_by(Day.day).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def _get_most_extreme_score(self, maximize: bool):
        func = sqlamax if maximize else sqlamin
        stmt = select(text("sub.word"), text("sub.date"), func(text("sub.avg"))).select_from(
            select(
                Day.word,
                Day.date,
                (sqlasum(Score.score) / count(Score.score)).label("avg")
            ).select_from(Day).join(
                Score, Day.id == Score.day_id
            ).where(Score.score != None).group_by(Day.id).subquery("sub")
        )
        return self.session.execute(stmt).one_or_none()

    def get_lowest_average_score(self):
        return self._get_most_extreme_score(False)

    def get_highest_average_score(self):
        return self._get_most_extreme_score(True)

    def mark_word_fake(self, date_to_mark: date, reported_by: int):
        day = self.get_day_entry(date_to_mark)
        self.session.add(FakeWord(day_id=day.id, reported_by=reported_by))
        self.session.flush()

        stmt = select(count("*")).select_from(FakeWord).where(FakeWord.day_id == day.id)
        return self.session.execute(stmt).scalar_one_or_none()

class DatabaseClient:
    def __init__(self, autocommit: bool = True):
        self.db_path = f"{os.environ['RESOURCES_PATH']}/database/database.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self.cursors: dict[int, DatabaseCursor] = {}
        self.autocommit = autocommit

        Base.metadata.create_all(bind=self.engine)

    def get_cursor(self) -> DatabaseCursor:
        thread_id = get_ident()
        if thread_id in self.cursors:
            cursor = self.cursors[thread_id]
            if cursor.session.connection().closed:
                del self.cursors[thread_id]
            else:
                return self.cursors[thread_id]

        cursor = DatabaseCursor(self.engine)
        self.cursors[get_ident()] = cursor

        return cursor

    def create_backup(self):
        without_ext = self.db_path.removesuffix(".db")
        backup_name = f"{without_ext}_backup.db"
        try:
            # Remove old backup if it exists.
            if os.path.exists(backup_name):
                os.remove(backup_name)

            copyfile(self.db_path, backup_name)
        except (OSError, IOError):
            logger.exception("Error when creating database backup!")

    def __enter__(self) -> DatabaseCursor:
        return self.get_cursor()

    def __exit__(self, exc_type, exc, tb):
        thread_id = get_ident()
        cursor = self.cursors.get(thread_id)
        if cursor:
            if self.autocommit:
                cursor.session.commit()

            cursor.session.close()
            del self.cursors[thread_id]

