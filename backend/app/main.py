from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from .db import Base, engine
from .api.routes import router, get_default_club
from .db import SessionLocal


app = FastAPI(title="Badminton Auto Matching")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        inspector = inspect(conn)
        if "clubs" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("clubs")}
            if "admin_code" not in columns:
                conn.execute(
                    text("ALTER TABLE clubs ADD COLUMN admin_code VARCHAR(20) DEFAULT '0000'")
                )
                conn.execute(text("UPDATE clubs SET admin_code='0000' WHERE admin_code IS NULL"))
            if "login_title" not in columns:
                conn.execute(
                    text("ALTER TABLE clubs ADD COLUMN login_title VARCHAR(120) DEFAULT '출석'")
                )
                conn.execute(text("UPDATE clubs SET login_title='출석' WHERE login_title IS NULL"))
            conn.commit()
        if "match_requests" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("match_requests")}
            if "opponent_team_1" not in columns:
                conn.execute(
                    text("ALTER TABLE match_requests ADD COLUMN opponent_team_1 VARCHAR(80)")
                )
            if "opponent_team_2" not in columns:
                conn.execute(
                    text("ALTER TABLE match_requests ADD COLUMN opponent_team_2 VARCHAR(80)")
                )
            if "is_deprioritized" not in columns:
                conn.execute(
                    text("ALTER TABLE match_requests ADD COLUMN is_deprioritized BOOLEAN DEFAULT 0")
                )
                conn.execute(
                    text("UPDATE match_requests SET is_deprioritized=0 WHERE is_deprioritized IS NULL")
                )
            conn.commit()
        if "members" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("members")}
            if "birth_year" not in columns:
                conn.execute(
                    text("ALTER TABLE members ADD COLUMN birth_year VARCHAR(2) DEFAULT '00'")
                )
                conn.execute(
                    text(
                        "UPDATE members SET birth_year=substr(strftime('%Y', birth_date),3,2) "
                        "WHERE birth_year IS NULL OR birth_year=''"
                    )
                )
                conn.commit()
            if "day_start_rank_position" not in columns:
                conn.execute(
                    text("ALTER TABLE members ADD COLUMN day_start_rank_position INTEGER")
                )
                conn.execute(
                    text("UPDATE members SET day_start_rank_position=rank_position WHERE day_start_rank_position IS NULL")
                )
                conn.commit()
            if "day_start_date" not in columns:
                conn.execute(text("ALTER TABLE members ADD COLUMN day_start_date DATE"))
                conn.execute(
                    text("UPDATE members SET day_start_date=date('now') WHERE day_start_date IS NULL")
                )
                conn.commit()
            if "last_rank_position" not in columns:
                conn.execute(text("ALTER TABLE members ADD COLUMN last_rank_position INTEGER"))
                conn.execute(
                    text("UPDATE members SET last_rank_position=rank_position WHERE last_rank_position IS NULL")
                )
                conn.commit()
            if "elo_rating" not in columns:
                conn.execute(text("ALTER TABLE members ADD COLUMN elo_rating FLOAT"))
                conn.execute(text("UPDATE members SET elo_rating=1500 WHERE elo_rating IS NULL"))
                conn.commit()
            if "win_streak" not in columns:
                conn.execute(text("ALTER TABLE members ADD COLUMN win_streak INTEGER DEFAULT 0"))
                conn.execute(text("UPDATE members SET win_streak=0 WHERE win_streak IS NULL"))
                conn.commit()
            if "last_match_at" not in columns:
                conn.execute(text("ALTER TABLE members ADD COLUMN last_match_at DATETIME"))
                conn.commit()
        if "login_sessions" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("login_sessions")}
            if "wait_started_at" not in columns:
                conn.execute(
                    text("ALTER TABLE login_sessions ADD COLUMN wait_started_at DATETIME")
                )
                conn.execute(
                    text("UPDATE login_sessions SET wait_started_at=login_at WHERE wait_started_at IS NULL")
                )
                conn.commit()
    db = SessionLocal()
    try:
        get_default_club(db)
    finally:
        db.close()


app.include_router(router, prefix="/api")
