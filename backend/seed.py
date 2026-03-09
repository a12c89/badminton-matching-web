import os
import random
from datetime import datetime, date, timedelta, UTC

from sqlalchemy import inspect, text
from app.db import Base, engine, SessionLocal
from app.models import (
    Club,
    Member,
    LoginSession,
    LessonQueue,
    DaySession,
    Match,
    MatchParticipant,
    MatchRequest,
)
from app.services.ranking import (
    compute_rank_group,
    assign_new_member_points,
    compute_seed_elo,
    recalculate_ranks,
)


def reset_database() -> None:
    db_url = str(engine.url)
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "", 1)
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except PermissionError:
                db = SessionLocal()
                try:
                    db.query(MatchParticipant).delete()
                    db.query(Match).delete()
                    db.query(MatchRequest).delete()
                    db.query(LoginSession).delete()
                    db.query(LessonQueue).delete()
                    db.query(DaySession).delete()
                    db.query(Member).delete()
                    db.query(Club).delete()
                    db.commit()
                finally:
                    db.close()
                with engine.connect() as conn:
                    inspector = inspect(conn)
                    if "members" in inspector.get_table_names():
                        columns = {col["name"] for col in inspector.get_columns("members")}
                        if "elo_rating" not in columns:
                            conn.execute(text("ALTER TABLE members ADD COLUMN elo_rating FLOAT"))
                        if "win_streak" not in columns:
                            conn.execute(text("ALTER TABLE members ADD COLUMN win_streak INTEGER DEFAULT 0"))
                        if "last_match_at" not in columns:
                            conn.execute(text("ALTER TABLE members ADD COLUMN last_match_at DATETIME"))
                        conn.commit()
                return
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_club(db) -> Club:
    club = Club(name="배드민턴 자동 매칭 시스템", admin_code="0000", login_title="출석")
    db.add(club)
    db.commit()
    db.refresh(club)
    return club


def _sample_local_grade() -> str:
    order = ["E", "D", "C", "B", "A"]
    # 평균을 C에 두고 정규분포 샘플
    idx = round(random.gauss(mu=2, sigma=0.9))
    idx = max(0, min(len(order) - 1, idx))
    return order[idx]


def _sample_national_grade(local_grade: str) -> str | None:
    # 전국 급수는 대체로 시도구보다 낮거나 비슷 (차이 최대 2)
    order = ["E", "D", "C", "B", "A", "S"]
    local_idx = order.index(local_grade)
    offset = random.choices([0, -1, -2], weights=[0.35, 0.45, 0.2], k=1)[0]
    national_idx = max(0, min(local_idx + offset, len(order) - 1))
    national = order[national_idx]
    if local_grade == "A":
        if national == "E":
            national = "C"
        if random.random() < 0.04:
            national = "S"
    return national


def seed_members(db, club_id: int, total: int = 90) -> list[Member]:
    random.seed(20260306)
    surnames = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "오", "한", "신", "서", "권"]
    male_given = [
        "민준",
        "서준",
        "도윤",
        "지후",
        "예준",
        "시우",
        "주원",
        "하준",
        "지호",
        "건우",
        "현우",
        "민재",
        "준호",
        "승민",
        "태윤",
    ]
    female_given = [
        "서연",
        "서윤",
        "지우",
        "하은",
        "윤서",
        "민서",
        "서현",
        "수아",
        "지민",
        "지윤",
        "채원",
        "하린",
        "나연",
        "유진",
        "예린",
    ]
    years = [f"{y:02d}" for y in list(range(70, 100)) + list(range(0, 6))]
    members: list[Member] = []
    for _ in range(total):
        gender = random.choice(["M", "F"])
        local_grade = _sample_local_grade()
        national_grade = _sample_national_grade(local_grade)
        is_player = False
        birth_year = random.choice(years)
        full_year = 2000 + int(birth_year) if int(birth_year) <= 39 else 1900 + int(birth_year)
        birth_date = date(full_year, 1, 1)
        given = male_given if gender == "M" else female_given
        name = f"{random.choice(surnames)}{random.choice(given)}"
        rank_group = compute_rank_group(local_grade, national_grade, is_player)
        points = assign_new_member_points(db, club_id, rank_group, national_grade, is_player)
        elo_seed = compute_seed_elo(local_grade, national_grade)
        member = Member(
            club_id=club_id,
            name=name,
            birth_date=birth_date,
            birth_year=birth_year,
            gender=gender,
            local_grade=local_grade,
            national_grade=national_grade,
            is_player=is_player,
            rank_group=rank_group,
            rating_points=points,
            elo_rating=elo_seed,
            win_streak=0,
        )
        db.add(member)
        db.flush()
        members.append(member)
    recalculate_ranks(db, club_id)
    today = date.today()
    for member in members:
        member.day_start_rank_position = member.rank_position
        member.day_start_date = today
        member.last_rank_position = member.rank_position
    db.commit()
    return members


def seed_sessions(db, club_id: int, members: list[Member], attendance_count: int = 30) -> None:
    """오늘 출석: attendance_count명이 0~1분 구간에 랜덤하게 로그인한 상태로 만듦.
    앱에서는 첫 로그인 시각 기준 20초가 지난 뒤부터 다음경기 큐를 짠다 (matching.py)."""
    now = datetime.now()
    active_members = random.sample(members, k=min(attendance_count, len(members)))
    window_seconds = 60  # 0~1분 사이에 랜덤 출석
    offsets = sorted(random.randint(0, window_seconds) for _ in active_members)
    login_times = [now + timedelta(seconds=offset) for offset in offsets]
    first_login_at = min(login_times) if login_times else now
    for member, login_at in zip(active_members, login_times):
        session = LoginSession(
            club_id=club_id,
            member_id=member.id,
            login_at=login_at,
            wait_started_at=login_at,
            is_active=True,
            is_in_match=False,
            is_guest=False,
        )
        db.add(session)
    day_session = DaySession(
        club_id=club_id,
        day_date=date.today(),
        first_login_at=first_login_at,
    )
    db.add(day_session)
    db.commit()


def seed_lessons(db, club_id: int, members: list[Member]) -> None:
    return


def main() -> None:
    reset_database()
    db = SessionLocal()
    try:
        club = seed_club(db)
        members = seed_members(db, club.id)
        seed_sessions(db, club.id, members, attendance_count=30)
        print(f"Seed 완료: 클럽 1개, 회원 {len(members)}명 (오늘 출석 {30}명)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
