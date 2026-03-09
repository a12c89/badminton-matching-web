import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
else:
    # Supabase pooler 한도 초과를 줄이기 위해 연결을 붙잡지 않도록 NullPool 사용
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        future=True,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
