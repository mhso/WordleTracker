from datetime import date
import os
from shutil import copyfile
from threading import get_ident

from loguru import logger
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.functions import max as sqlamax

from wordle_tracker.models import Base, Day

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

