from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, date
from itertools import combinations
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from ..models import (
    Club,
    DaySession,
    LoginSession,
    Match,
    MatchParticipant,
    Member,
    MatchRequest,
)
from .lesson import (
    format_member_label,
    format_waiting_label,
)
from .ranking import GRADE_ORDER


@dataclass
class MatchCandidate:
    members: List[Member]
    team_a: List[Member]
    team_b: List[Member]
    score: float
    is_mixed: bool


WAITING_WEIGHT = 20
BALANCE_WEIGHT = 200
MIX_OVER_PENALTY = 200
MIX_UNDER_BONUS = 120
FORCE_MIX_PENALTY = 1_000_000


def ensure_day_session(db: Session, club_id: int, day_date: date) -> DaySession:
    day_session = (
        db.query(DaySession)
        .filter(DaySession.club_id == club_id, DaySession.day_date == day_date)
        .first()
    )
    if not day_session:
        day_session = DaySession(club_id=club_id, day_date=day_date, first_login_at=None)
        db.add(day_session)
        db.flush()
    return day_session


def _skill_score(member: Member) -> int:
    local_grade = member.rank_group[0] if member.rank_group else "E"
    local = GRADE_ORDER.get(local_grade, 1)
    national = GRADE_ORDER.get((member.national_grade or "E").upper(), 1)
    return local + national * 10


def _history_pairs(
    db: Session, club_id: int, day_date: date
) -> Tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    matches = (
        db.query(MatchParticipant)
        .join(Match, Match.id == MatchParticipant.match_id)
        .filter(Match.club_id == club_id, Match.day_date == day_date)
        .all()
    )
    teammate_pairs: set[tuple[int, int]] = set()
    opponent_pairs: set[tuple[int, int]] = set()
    match_groups: Dict[int, List[MatchParticipant]] = {}
    for mp in matches:
        match_groups.setdefault(mp.match_id, []).append(mp)
    for participants in match_groups.values():
        team_a = [p.member_id for p in participants if p.team == "A"]
        team_b = [p.member_id for p in participants if p.team == "B"]
        for a1, a2 in combinations(team_a, 2):
            teammate_pairs.add(tuple(sorted((a1, a2))))
        for b1, b2 in combinations(team_b, 2):
            teammate_pairs.add(tuple(sorted((b1, b2))))
        for a in team_a:
            for b in team_b:
                opponent_pairs.add(tuple(sorted((a, b))))
    return teammate_pairs, opponent_pairs


def _member_balance_counts(
    db: Session,
    club_id: int,
    day_date: date,
    member_ids: set[int],
) -> Dict[int, tuple[int, int]]:
    counts = {member_id: (0, 0) for member_id in member_ids}
    if not member_ids:
        return counts
    matches = (
        db.query(Match)
        .filter(Match.club_id == club_id, Match.day_date == day_date)
        .all()
    )
    if not matches:
        return counts
    all_ids = {
        member_id
        for match in matches
        for member_id in [int(x) for x in (match.team_a + "," + match.team_b).split(",") if x]
        if member_id in member_ids
    }
    if not all_ids:
        return counts
    members = db.query(Member).filter(Member.id.in_(all_ids)).all()
    member_map = {m.id: m for m in members}
    for match in matches:
        ids = [int(x) for x in (match.team_a + "," + match.team_b).split(",") if x]
        match_members = [member_map[mid] for mid in ids if mid in member_map]
        if not match_members:
            continue
        genders = {m.gender for m in match_members}
        is_mixed = len(genders) > 1
        for m in match_members:
            same_count, mixed_count = counts.get(m.id, (0, 0))
            if is_mixed:
                mixed_count += 1
            else:
                same_count += 1
            counts[m.id] = (same_count, mixed_count)
    return counts


def _needs_mixed_forced(counts: Dict[int, tuple[int, int]], member_ids: List[int]) -> bool:
    for member_id in member_ids:
        same_count, mixed_count = counts.get(member_id, (0, 0))
        if same_count - mixed_count >= 2:
            return True
    return False


def _available_types(candidates: List[Member]) -> List[str]:
    male_count = sum(1 for m in candidates if m.gender == "M")
    female_count = sum(1 for m in candidates if m.gender == "F")
    types: List[str] = []
    if male_count >= 4:
        types.append("MM")
    if female_count >= 4:
        types.append("FF")
    if male_count >= 2 and female_count >= 2:
        types.append("MIX")
    return types


def _select_group_by_type(
    anchor: Member,
    pool: List[Member],
    match_type: str,
    teammate_pairs: set[tuple[int, int]],
    opponent_pairs: set[tuple[int, int]],
    waiting_index: Dict[int, int],
    balance_counts: Dict[int, tuple[int, int]] | None,
) -> MatchCandidate | None:
    others = [m for m in pool if m.id != anchor.id]
    if len(others) < 3:
        return None
    best: MatchCandidate | None = None
    for group in combinations(others, 3):
        members = [anchor, *group]
        if match_type == "MM" and any(m.gender != "M" for m in members):
            continue
        if match_type == "FF" and any(m.gender != "F" for m in members):
            continue
        if match_type == "MIX":
            male_count = sum(1 for m in members if m.gender == "M")
            female_count = sum(1 for m in members if m.gender == "F")
            if not (male_count == 2 and female_count == 2):
                continue
        candidate = _candidate_score(
            members,
            teammate_pairs,
            opponent_pairs,
            waiting_index,
            balance_counts=balance_counts,
        )
        team_type_a = _team_type(candidate.team_a)
        team_type_b = _team_type(candidate.team_b)
        if team_type_a != team_type_b or team_type_a != match_type:
            continue
        if not best or candidate.score < best.score:
            best = candidate
    return best


def _pairing_score(
    team_a: List[Member],
    team_b: List[Member],
    teammate_pairs: set[tuple[int, int]],
    opponent_pairs: set[tuple[int, int]],
) -> float:
    skill_a = sum(_skill_score(m) for m in team_a) / 2
    skill_b = sum(_skill_score(m) for m in team_b) / 2
    rank_a = sum(m.rank_position for m in team_a) / 2
    rank_b = sum(m.rank_position for m in team_b) / 2
    # 등수 간 거리 우선
    score = abs(rank_a - rank_b) * 10 + abs(skill_a - skill_b)
    for pair in combinations([m.id for m in team_a], 2):
        if tuple(sorted(pair)) in teammate_pairs:
            score += 150
    for pair in combinations([m.id for m in team_b], 2):
        if tuple(sorted(pair)) in teammate_pairs:
            score += 150
    for a in team_a:
        for b in team_b:
            if tuple(sorted((a.id, b.id))) in opponent_pairs:
                score += 400
    team_type_a = _team_type(team_a)
    team_type_b = _team_type(team_b)
    if team_type_a != team_type_b:
        score += 500
    return score


def _team_type(team: List[Member]) -> str:
    males = sum(1 for m in team if m.gender == "M")
    females = sum(1 for m in team if m.gender == "F")
    if males == 2:
        return "MM"
    if females == 2:
        return "FF"
    return "MIX"


def _best_pairing(
    members: List[Member],
    teammate_pairs: set[tuple[int, int]],
    opponent_pairs: set[tuple[int, int]],
) -> Tuple[List[Member], List[Member], float]:
    pairings = [
        ([members[0], members[1]], [members[2], members[3]]),
        ([members[0], members[2]], [members[1], members[3]]),
        ([members[0], members[3]], [members[1], members[2]]),
    ]
    best_score = float("inf")
    best_pairing = pairings[0]
    for team_a, team_b in pairings:
        score = _pairing_score(team_a, team_b, teammate_pairs, opponent_pairs)
        if score < best_score:
            best_score = score
            best_pairing = (team_a, team_b)
    return best_pairing[0], best_pairing[1], best_score


def _candidate_score(
    members: List[Member],
    teammate_pairs: set[tuple[int, int]],
    opponent_pairs: set[tuple[int, int]],
    waiting_index: Dict[int, int],
    balance_counts: Dict[int, tuple[int, int]] | None = None,
    type_counts: Dict[str, int] | None = None,
    mixed_penalty: float = 0,
) -> MatchCandidate:
    team_a, team_b, score = _best_pairing(members, teammate_pairs, opponent_pairs)
    rank_positions = [m.rank_position for m in members]
    spread = max(rank_positions) - min(rank_positions)
    score += spread * 5
    score += sum(waiting_index.get(m.id, 0) for m in members) * WAITING_WEIGHT
    if balance_counts:
        is_mixed_match = len({m.gender for m in members}) > 1
        if not is_mixed_match and _needs_mixed_forced(balance_counts, [m.id for m in members]):
            score += FORCE_MIX_PENALTY
        for m in members:
            same_count, mixed_count = balance_counts.get(m.id, (0, 0))
            if is_mixed_match:
                mixed_count += 1
            else:
                same_count += 1
            if mixed_count > same_count:
                score += (mixed_count - same_count) * MIX_OVER_PENALTY
            elif same_count > mixed_count:
                score -= (same_count - mixed_count) * MIX_UNDER_BONUS
    genders = {m.gender for m in members}
    is_mixed = len(genders) > 1
    return MatchCandidate(members=members, team_a=team_a, team_b=team_b, score=score, is_mixed=is_mixed)


def _select_best_group(
    candidates: List[Member],
    teammate_pairs: set[tuple[int, int]],
    opponent_pairs: set[tuple[int, int]],
    waiting_index: Dict[int, int],
    prefer_same_gender: bool,
) -> MatchCandidate | None:
    if len(candidates) < 4:
        return None
    pool = candidates[:12]
    best: MatchCandidate | None = None
    mixed_penalty = 0
    for group in combinations(pool, 4):
        candidate = _candidate_score(
            list(group),
            teammate_pairs,
            opponent_pairs,
            waiting_index,
            balance_counts=None,
            type_counts=None,
            mixed_penalty=mixed_penalty,
        )
        if not best or candidate.score < best.score:
            best = candidate
    return best


def _select_group_by_waiting_order(
    candidates: List[Member],
) -> List[Member] | None:
    if len(candidates) < 4:
        return None
    return candidates[:4]


def _select_group_by_anchor(
    candidates: List[Member],
    teammate_pairs: set[tuple[int, int]],
    opponent_pairs: set[tuple[int, int]],
    waiting_index: Dict[int, int],
    pool_size: int = 12,
    desired_type: str | None = None,
    type_counts: Dict[str, int] | None = None,
    balance_counts: Dict[int, tuple[int, int]] | None = None,
) -> MatchCandidate | None:
    if len(candidates) < 4:
        return None
    anchor = candidates[0]
    pool = candidates[:pool_size]
    available_types = _available_types(pool)
    if desired_type and desired_type in available_types:
        available_types = [desired_type]
    best: MatchCandidate | None = None
    for match_type in available_types:
        candidate = _select_group_by_type(
            anchor,
            pool,
            match_type,
            teammate_pairs,
            opponent_pairs,
            waiting_index,
            balance_counts,
        )
        if candidate and (not best or candidate.score < best.score):
            best = candidate
    return best


def _match_type_from_members(members: List[Member]) -> str:
    males = sum(1 for m in members if m.gender == "M")
    females = sum(1 for m in members if m.gender == "F")
    if males == 4:
        return "MM"
    if females == 4:
        return "FF"
    if males == 2 and females == 2:
        return "MIX"
    return "MIX_FALLBACK"


def _desired_match_type(
    candidates: List[Member],
    type_counts: Dict[str, int],
) -> str | None:
    if len(candidates) < 4:
        return None
    anchor = candidates[0]
    male_count = sum(1 for m in candidates if m.gender == "M")
    female_count = sum(1 for m in candidates if m.gender == "F")
    available: list[str] = []
    if anchor.gender == "M":
        if male_count >= 4:
            available.append("MM")
        if male_count >= 2 and female_count >= 2:
            available.append("MIX")
    elif anchor.gender == "F":
        if female_count >= 4:
            available.append("FF")
        if male_count >= 2 and female_count >= 2:
            available.append("MIX")
    else:
        if male_count >= 2 and female_count >= 2:
            available.append("MIX")
    if not available:
        return None
    return min(available, key=lambda key: (type_counts.get(key, 0), key))


def _member_match_type_counts(
    db: Session,
    club_id: int,
    day_date: date,
    member_id: int,
) -> Dict[str, int]:
    matches = (
        db.query(Match)
        .filter(
            Match.club_id == club_id,
            Match.day_date == day_date,
            Match.status.in_(["active", "scheduled", "completed"]),
        )
        .all()
    )
    counts = {"MM": 0, "FF": 0, "MIX": 0}
    if not matches:
        return counts
    member_ids = {
        member_id
        for match in matches
        for member_id in [int(x) for x in (match.team_a + "," + match.team_b).split(",") if x]
    }
    members = db.query(Member).filter(Member.id.in_(member_ids)).all()
    member_map = {m.id: m for m in members}
    for match in matches:
        ids = [int(x) for x in (match.team_a + "," + match.team_b).split(",") if x]
        if member_id not in ids:
            continue
        match_members = [member_map[mid] for mid in ids if mid in member_map]
        match_type = _match_type_from_members(match_members)
        if match_type in counts:
            counts[match_type] += 1
    return counts


def _match_type_counts(db: Session, club_id: int, day_date: date) -> Dict[str, int]:
    matches = (
        db.query(Match)
        .filter(
            Match.club_id == club_id,
            Match.day_date == day_date,
            Match.status.in_(["active", "scheduled", "completed"]),
        )
        .all()
    )
    counts = {"MM": 0, "FF": 0, "MIX": 0}
    if not matches:
        return counts
    member_ids = {
        member_id
        for match in matches
        for member_id in [int(x) for x in (match.team_a + "," + match.team_b).split(",") if x]
    }
    members = db.query(Member).filter(Member.id.in_(member_ids)).all()
    member_map = {m.id: m for m in members}
    for match in matches:
        ids = [int(x) for x in (match.team_a + "," + match.team_b).split(",") if x]
        match_members = [member_map[mid] for mid in ids if mid in member_map]
        match_type = _match_type_from_members(match_members)
        if match_type in counts:
            counts[match_type] += 1
    return counts


def _eligible_members(
    db: Session,
    club_id: int,
    day_date: date,
    now: datetime,
) -> List[Member]:
    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        return []
    sessions = (
        db.query(LoginSession, Member)
        .join(Member, LoginSession.member_id == Member.id)
        .filter(
            LoginSession.club_id == club_id,
            LoginSession.is_active.is_(True),
            LoginSession.is_in_match.is_(False),
        )
        .order_by(LoginSession.login_at.asc())
        .all()
    )
    unique: Dict[int, Member] = {}
    for _, member in sessions:
        if member.id not in unique:
            unique[member.id] = member
    members = list(unique.values())
    return members


def _requested_member_ids(db: Session, club_id: int, day_date: date) -> tuple[set[int], set[int]]:
    requests = (
        db.query(MatchRequest)
        .filter(MatchRequest.club_id == club_id, MatchRequest.day_date == day_date)
        .all()
    )
    requested = {req.member_id for req in requests if not req.is_deprioritized}
    deprioritized = {req.member_id for req in requests if req.is_deprioritized}
    return requested, deprioritized


def _request_groups(db: Session, club_id: int, day_date: date) -> list[dict]:
    requests = (
        db.query(MatchRequest)
        .filter(
            MatchRequest.club_id == club_id,
            MatchRequest.day_date == day_date,
            MatchRequest.target_member_id.isnot(None),
            MatchRequest.is_deprioritized.is_(False),
        )
        .all()
    )
    groups: list[dict] = []
    for req in requests:
        if not req.target_member_id:
            continue
        ids: list[int] = [req.member_id, req.target_member_id]
        for name in [req.opponent_team_1, req.opponent_team_2]:
            if not name:
                continue
            opponent = (
                db.query(Member)
                .filter(Member.club_id == club_id, Member.name == name)
                .first()
            )
            if opponent:
                ids.append(opponent.id)
        unique_ids = list(dict.fromkeys(ids))
        if len(unique_ids) >= 2:
            groups.append({"member_ids": unique_ids})
    return groups


def generate_matches(
    db: Session,
    club_id: int,
    now: datetime,
    court_numbers: List[int] | None = None,
    exclude_member_ids: set[int] | None = None,
    force_create: bool = False,
) -> Tuple[List[Match], List[MatchCandidate], List[dict], List[str]]:
    day_date = now.date()
    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        return [], [], [], []

    day_session = ensure_day_session(db, club_id, day_date)
    members = _eligible_members(db, club_id, day_date, now)
    if exclude_member_ids:
        members = [m for m in members if m.id not in exclude_member_ids]
    request_groups = _request_groups(db, club_id, day_date)
    request_ids = {mid for group in request_groups for mid in group["member_ids"]}
    if request_ids:
        normal = [m for m in members if m.id not in request_ids]
        requested = [m for m in members if m.id in request_ids]
        # 요청자/상대가 대기자에 들어온 경우만 후순위로 이동
        members = normal + requested
    lesson_ids: set[int] = set()
    waiting_labels = [
        {
            "label": format_waiting_label(m),
            "gender": m.gender,
            "is_lesson": m.id in lesson_ids,
        }
        for m in members
    ]
    lesson_labels = []
    # 대기자가 많은데 다음경기가 없을 때 force_create로 20초/first_login_at 조건 무시
    if not force_create:
        if not day_session.first_login_at:
            return [], [], waiting_labels, lesson_labels
        if now < day_session.first_login_at + timedelta(seconds=20):
            return [], [], waiting_labels, lesson_labels
    elif not day_session.first_login_at and len(members) >= 4:
        day_session.first_login_at = now - timedelta(seconds=21)

    teammate_pairs, opponent_pairs = _history_pairs(db, club_id, day_date)
    waiting_index = {m.id: idx for idx, m in enumerate(members)}
    type_counts = _match_type_counts(db, club_id, day_date)
    balance_counts = _member_balance_counts(db, club_id, day_date, {m.id for m in members})
    # 패널티 제거: 대기 순서만 사용
    eligible_ids = {m.id for m in members}
    ready_groups = [
        [m for m in members if m.id in group["member_ids"]]
        for group in request_groups
        if all(member_id in eligible_ids for member_id in group["member_ids"])
    ]
    pending_ids = {
        member_id
        for group in request_groups
        if not all(member_id in eligible_ids for member_id in group["member_ids"])
        for member_id in group["member_ids"]
    }
    matches: List[Match] = []
    used_member_ids: set[int] = set()
    courts = court_numbers if court_numbers is not None else [1, 2, 3]
    court_index = 0

    def take_candidate(group: MatchCandidate) -> None:
        nonlocal court_index
        if court_index >= len(courts):
            return
        match = Match(
            club_id=club_id,
            day_date=day_date,
            court_number=courts[court_index],
            status="active",
            start_at=now,
            team_a=",".join(str(m.id) for m in group.team_a),
            team_b=",".join(str(m.id) for m in group.team_b),
        )
        matches.append(match)
        for m in group.members:
            used_member_ids.add(m.id)
        court_index += 1

    while court_index < len(courts):
        remaining_candidates = [m for m in members if m.id not in used_member_ids]
        candidate = _select_group_by_anchor(
            remaining_candidates,
            teammate_pairs,
            opponent_pairs,
            waiting_index,
            desired_type=None,
            type_counts=type_counts,
            balance_counts=balance_counts,
        )
        if not candidate:
            break
        take_candidate(candidate)
        match_type = _match_type_from_members(candidate.members)
        if match_type in type_counts:
            type_counts[match_type] += 1

    waiting_members = [m for m in members if m.id not in used_member_ids]
    waiting_labels = [
        {
            "label": format_waiting_label(m),
            "gender": m.gender,
            "is_lesson": m.id in lesson_ids,
        }
        for m in waiting_members
    ]
    matching_pool = [m for m in waiting_members if m.id not in pending_ids]
    next_candidates = build_next_match_candidates(
        db,
        club_id,
        day_date,
        matching_pool,
        teammate_pairs,
        opponent_pairs,
        type_counts=type_counts,
        balance_counts=balance_counts,
        ready_groups=ready_groups,
        limit=3,
    )
    return matches, next_candidates, waiting_labels, lesson_labels


def build_next_match_candidates(
    db: Session,
    club_id: int,
    day_date: date,
    members: List[Member],
    teammate_pairs: set[tuple[int, int]],
    opponent_pairs: set[tuple[int, int]],
    type_counts: Dict[str, int] | None = None,
    balance_counts: Dict[int, tuple[int, int]] | None = None,
    ready_groups: list[list[Member]] | None = None,
    limit: int = 3,
) -> List[MatchCandidate]:
    candidates: List[MatchCandidate] = []
    remaining = members[:]
    type_counts = dict(type_counts or {"MM": 0, "FF": 0, "MIX": 0})
    if ready_groups:
        for group in ready_groups:
            if len(candidates) >= limit:
                break
            if any(m not in remaining for m in group) or len(group) < 4:
                continue
            candidate = _candidate_score(
                group,
                teammate_pairs,
                opponent_pairs,
                {m.id: 0 for m in remaining},
                balance_counts=balance_counts,
                type_counts=type_counts,
            )
            candidates.append(candidate)
            match_type = _match_type_from_members(candidate.members)
            if match_type in type_counts:
                type_counts[match_type] += 1
            used_ids = {m.id for m in candidate.members}
            remaining = [m for m in remaining if m.id not in used_ids]
    while len(candidates) < limit and len(remaining) >= 4:
        waiting_index = {m.id: idx for idx, m in enumerate(remaining)}
        candidate = _select_group_by_anchor(
            remaining,
            teammate_pairs,
            opponent_pairs,
            waiting_index,
            desired_type=None,
            type_counts=type_counts,
            balance_counts=balance_counts,
        )
        # 인원이 적을 때: 이상적인 조합(MM/FF/MIX 2-2)이 없어도 대기 순서대로 4명 뽑아서 경기 생성 (한 번 같이 한 사람끼리도 허용)
        if not candidate and len(remaining) >= 4:
            fallback_members = remaining[:4]
            team_a, team_b, _ = _best_pairing(
                fallback_members, teammate_pairs, opponent_pairs
            )
            candidate = MatchCandidate(
                members=fallback_members,
                team_a=team_a,
                team_b=team_b,
                score=9999.0,
                is_mixed=len({m.gender for m in fallback_members}) > 1,
            )
        if not candidate:
            break
        candidates.append(candidate)
        match_type = _match_type_from_members(candidate.members)
        if match_type in type_counts:
            type_counts[match_type] += 1
        used_ids = {m.id for m in candidate.members}
        remaining = [m for m in remaining if m.id not in used_ids]
    return candidates


def build_lesson_lines(schedule, now):
    from .lesson import build_lesson_display

    return build_lesson_display(schedule, now)
