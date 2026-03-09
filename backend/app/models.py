from datetime import datetime, date, time
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Boolean,
    ForeignKey,
    Time,
    Float,
)
from sqlalchemy.orm import relationship
from .db import Base


class Club(Base):
    __tablename__ = "clubs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False)
    admin_code = Column(String(20), default="0000", nullable=False)
    login_title = Column(String(120), default="출석", nullable=False)
    session_start_time = Column(Time, default=time(18, 30), nullable=False)
    session_end_time = Column(Time, default=time(21, 30), nullable=False)
    lesson_start_time = Column(Time, default=time(18, 40), nullable=False)
    match_duration_minutes = Column(Integer, default=25, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    members = relationship("Member", back_populates="club")


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    name = Column(String(80), nullable=False)
    birth_date = Column(Date, nullable=False)
    birth_year = Column(String(2), nullable=False, default="00")
    gender = Column(String(1), nullable=False)  # M/F/X
    local_grade = Column(String(2), nullable=True)
    national_grade = Column(String(2), nullable=True)
    is_player = Column(Boolean, default=False, nullable=False)
    rank_group = Column(String(2), nullable=False)
    rating_points = Column(Integer, default=0, nullable=False)
    elo_rating = Column(Float, nullable=True)
    win_streak = Column(Integer, default=0, nullable=False)
    last_match_at = Column(DateTime, nullable=True)
    rank_position = Column(Integer, default=0, nullable=False)
    day_start_rank_position = Column(Integer, nullable=True)
    day_start_date = Column(Date, nullable=True)
    last_rank_position = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    club = relationship("Club", back_populates="members")
    sessions = relationship("LoginSession", back_populates="member")


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id = Column(Integer, primary_key=True, index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    login_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    wait_started_at = Column(DateTime, nullable=True)
    logout_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_guest = Column(Boolean, default=False, nullable=False)
    is_in_match = Column(Boolean, default=False, nullable=False)

    member = relationship("Member", back_populates="sessions")


class DaySession(Base):
    __tablename__ = "day_sessions"

    id = Column(Integer, primary_key=True, index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    day_date = Column(Date, nullable=False)
    first_login_at = Column(DateTime, nullable=True)


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    day_date = Column(Date, nullable=False)
    court_number = Column(Integer, nullable=True)
    status = Column(String(20), default="scheduled", nullable=False)
    queue_position = Column(Integer, nullable=True)
    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)
    team_a = Column(String, nullable=False)  # comma-separated member ids
    team_b = Column(String, nullable=False)
    score_a = Column(Integer, nullable=True)
    score_b = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MatchParticipant(Base):
    __tablename__ = "match_participants"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    team = Column(String(1), nullable=False)  # A/B
    day_date = Column(Date, nullable=False)


class LessonQueue(Base):
    __tablename__ = "lesson_queue"

    id = Column(Integer, primary_key=True, index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    order_index = Column(Integer, nullable=False)
    group_size = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MatchRequest(Base):
    __tablename__ = "match_requests"

    id = Column(Integer, primary_key=True, index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    target_member_id = Column(Integer, ForeignKey("members.id"), nullable=True)
    opponent_team_1 = Column(String(80), nullable=True)
    opponent_team_2 = Column(String(80), nullable=True)
    note = Column(String(200), nullable=True)
    day_date = Column(Date, nullable=False)
    is_deprioritized = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
