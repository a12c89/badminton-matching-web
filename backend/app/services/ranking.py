from datetime import datetime
import math
from typing import Iterable
from sqlalchemy.orm import Session
from ..models import Member


GRADE_ORDER = {"S": 6, "A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
ELO_BASE = 1000
LOCAL_WEIGHT = 50
NATIONAL_WEIGHT = 200
K_BASE = 24
STREAK_MULT = 1.1
DECAY_DAYS = 30


def compute_rank_group(local_grade: str | None, national_grade: str | None, is_player: bool) -> str:
    local = (local_grade or "E").upper()
    national = (national_grade or "E").upper()
    if local not in GRADE_ORDER:
        local = "E"
    if national not in GRADE_ORDER:
        national = "E"
    return f"{local}{national}"


def compute_initial_points(rank_group: str, national_grade: str | None, is_player: bool) -> int:
    local = rank_group[0] if rank_group else "E"
    national = rank_group[1] if len(rank_group) > 1 else "E"
    local_score = GRADE_ORDER.get(local, 1)
    national_score = GRADE_ORDER.get(national, 1)
    return local_score * 100 + national_score * 10


def compute_seed_elo(local_grade: str | None, national_grade: str | None) -> float:
    local = (local_grade or "E").upper()
    national = (national_grade or "E").upper()
    local_score = GRADE_ORDER.get(local, 1)
    national_score = GRADE_ORDER.get(national, 1)
    return float(ELO_BASE + local_score * LOCAL_WEIGHT + national_score * NATIONAL_WEIGHT)


def assign_new_member_points(
    db: Session, club_id: int, rank_group: str, national_grade: str | None, is_player: bool
) -> int:
    members = (
        db.query(Member)
        .filter(Member.club_id == club_id, Member.rank_group == rank_group)
        .all()
    )
    if not members:
        return compute_initial_points(rank_group, national_grade, is_player)
    min_points = min(m.rating_points for m in members)
    return min_points - 1


def _grade_strength(member: Member) -> int:
    if member.is_player:
        return 1000
    local = (member.local_grade or "E").upper()
    national = (member.national_grade or "E").upper()
    local_score = GRADE_ORDER.get(local, 1)
    national_score = GRADE_ORDER.get(national, 1)
    return local_score * 100 + national_score * 10


def recalculate_ranks(db: Session, club_id: int) -> None:
    members = db.query(Member).filter(Member.club_id == club_id).all()
    for member in members:
        member.last_rank_position = member.rank_position
        if member.elo_rating is None:
            member.elo_rating = compute_seed_elo(member.local_grade, member.national_grade)
    members.sort(
        key=lambda m: (
            -(m.elo_rating or 0),
            m.created_at,
        )
    )
    for idx, member in enumerate(members, start=1):
        member.rank_position = idx
        member.updated_at = datetime.utcnow()
    db.flush()


def apply_match_result(
    db: Session,
    club_id: int,
    team_a: Iterable[Member],
    team_b: Iterable[Member],
    score_a: int,
    score_b: int,
    match_time: datetime | None = None,
) -> None:
    team_a = list(team_a)
    team_b = list(team_b)
    if not team_a or not team_b:
        return
    match_time = match_time or datetime.utcnow()
    participants = team_a + team_b
    for member in participants:
        if member.elo_rating is None:
            member.elo_rating = compute_seed_elo(member.local_grade, member.national_grade)
        if member.last_match_at:
            days = (match_time - member.last_match_at).total_seconds() / 86400
            decay = math.exp(-days / DECAY_DAYS)
            seed = compute_seed_elo(member.local_grade, member.national_grade)
            member.elo_rating = seed + (member.elo_rating - seed) * decay
        member.last_match_at = match_time

    team_a_elo = sum(m.elo_rating or 0 for m in team_a) / len(team_a)
    team_b_elo = sum(m.elo_rating or 0 for m in team_b) / len(team_b)
    expected_a = 1 / (1 + 10 ** ((team_b_elo - team_a_elo) / 400))
    expected_b = 1 - expected_a

    if score_a == score_b:
        actual_a = 0.5
        actual_b = 0.5
        winners = []
        losers = []
    elif score_a > score_b:
        actual_a = 1.0
        actual_b = 0.0
        winners = team_a
        losers = team_b
    else:
        actual_a = 0.0
        actual_b = 1.0
        winners = team_b
        losers = team_a

    for member in team_a:
        streak = max(0, member.win_streak or 0)
        k = K_BASE * (STREAK_MULT ** max(0, streak - 1)) if member in winners else K_BASE
        member.elo_rating = (member.elo_rating or 0) + k * (actual_a - expected_a)
        member.updated_at = datetime.utcnow()
    for member in team_b:
        streak = max(0, member.win_streak or 0)
        k = K_BASE * (STREAK_MULT ** max(0, streak - 1)) if member in winners else K_BASE
        member.elo_rating = (member.elo_rating or 0) + k * (actual_b - expected_b)
        member.updated_at = datetime.utcnow()

    for member in winners:
        member.win_streak = (member.win_streak or 0) + 1
    for member in losers:
        member.win_streak = 0

    recalculate_ranks(db, club_id)
