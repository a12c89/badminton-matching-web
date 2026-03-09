from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..db import get_db
from ..models import Club, Member, LoginSession, LessonQueue, Match, MatchParticipant, MatchRequest
from ..schemas import (
    ClubUpdate,
    ClubOut,
    MemberCreate,
    MemberUpdateGrade,
    MemberUpdate,
    MemberUpdateByIdentity,
    MemberOut,
    LoginRequest,
    LoginSessionOut,
    LogoutRequest,
    LessonQueueItemCreate,
    LessonQueueReorder,
    AdminVerify,
    AdminCodeUpdate,
    AdminMatchTeamsUpdate,
    MatchFinishRequest,
    MatchRequestCreate,
    PublicRankingItem,
    DashboardOut,
    CourtDisplay,
    TeamDisplay,
    WaitingItem,
)
from ..services.ranking import (
    compute_rank_group,
    assign_new_member_points,
    compute_seed_elo,
    recalculate_ranks,
    apply_match_result,
)
from ..services.lesson import (
    format_member_label,
    format_waiting_label,
    get_lesson_schedule,
    build_lesson_display,
)
from ..services.matching import ensure_day_session, generate_matches


router = APIRouter()

DEFAULT_CLUB_ID = 1


def _active_member_ids(db: Session, club_id: int, day_date: date) -> set[int]:
    active_matches = (
        db.query(Match.id)
        .filter(Match.club_id == club_id, Match.day_date == day_date, Match.status == "active")
        .all()
    )
    match_ids = [m.id for m in active_matches]
    if not match_ids:
        return set()
    participants = (
        db.query(MatchParticipant.member_id)
        .filter(MatchParticipant.match_id.in_(match_ids))
        .all()
    )
    return {p.member_id for p in participants}


def _normalize_birth_year(value: str | None) -> str:
    if not value:
        raise HTTPException(status_code=400, detail="생년은 YY 형식으로 입력해주세요.")
    cleaned = value.strip()
    if len(cleaned) == 6 and cleaned.isdigit():
        cleaned = cleaned[-2:]
    if len(cleaned) != 2 or not cleaned.isdigit():
        raise HTTPException(status_code=400, detail="생년은 YY 형식으로 입력해주세요.")
    return cleaned


def _available_courts(db: Session, club_id: int, day_date: date) -> list[int]:
    active = (
        db.query(Match.court_number)
        .filter(Match.club_id == club_id, Match.day_date == day_date, Match.status == "active")
        .all()
    )
    active_numbers = {item.court_number for item in active if item.court_number}
    return [court for court in (1, 2, 3) if court not in active_numbers]


def _member_exists(
    db: Session, club_id: int, name: str, birth_year: str, exclude_member_id: int | None = None
) -> bool:
    query = db.query(Member).filter(
        Member.club_id == club_id, Member.name == name, Member.birth_year == birth_year
    )
    if exclude_member_id is not None:
        query = query.filter(Member.id != exclude_member_id)
    return db.query(query.exists()).scalar() or False


def _create_matches(db: Session, club_id: int, matches: list[Match]) -> int:
    if not matches:
        return 0
    active_ids = _active_member_ids(db, club_id, matches[0].day_date)
    created = 0
    for match in matches:
        team_a_ids = [int(x) for x in match.team_a.split(",") if x]
        team_b_ids = [int(x) for x in match.team_b.split(",") if x]
        if set(team_a_ids + team_b_ids).intersection(active_ids):
            continue
        db.add(match)
        db.flush()
        created += 1
        for member_id in team_a_ids:
            db.add(
                MatchParticipant(
                    match_id=match.id, member_id=member_id, team="A", day_date=match.day_date
                )
            )
            session = (
                db.query(LoginSession)
                .filter(LoginSession.member_id == member_id, LoginSession.is_active.is_(True))
                .first()
            )
            if session:
                session.is_in_match = True
        for member_id in team_b_ids:
            db.add(
                MatchParticipant(
                    match_id=match.id, member_id=member_id, team="B", day_date=match.day_date
                )
            )
            session = (
                db.query(LoginSession)
                .filter(LoginSession.member_id == member_id, LoginSession.is_active.is_(True))
                .first()
            )
            if session:
                session.is_in_match = True
        active_ids.update(team_a_ids + team_b_ids)
    db.commit()
    return created


def _cleanup_stale_sessions(db: Session, club_id: int, today: date) -> None:
    stale_sessions = (
        db.query(LoginSession)
        .filter(LoginSession.club_id == club_id, LoginSession.is_active.is_(True))
        .all()
    )
    changed = False
    for session in stale_sessions:
        if session.login_at.date() < today:
            session.is_active = False
            session.is_in_match = False
            session.logout_at = datetime.utcnow()
            changed = True
    if changed:
        db.commit()


def _remove_member_from_today_flow(db: Session, club_id: int, member_id: int, today: date) -> None:
    """로그아웃 회원을 오늘의 대기/다음경기/코트 흐름에서 완전히 제거합니다."""
    now = datetime.now()
    matches = (
        db.query(Match)
        .filter(
            Match.club_id == club_id,
            Match.day_date == today,
            Match.status.in_(("active", "scheduled")),
        )
        .all()
    )
    removed_match_ids: list[int] = []
    affected_member_ids: set[int] = set()
    for match in matches:
        ids = [int(x) for x in (match.team_a + "," + match.team_b).split(",") if x]
        if member_id not in ids:
            continue
        removed_match_ids.append(match.id)
        affected_member_ids.update(ids)
        db.delete(match)

    if removed_match_ids:
        db.query(MatchParticipant).filter(MatchParticipant.match_id.in_(removed_match_ids)).delete(
            synchronize_session=False
        )
        remaining = (
            db.query(Match)
            .filter(Match.club_id == club_id, Match.day_date == today, Match.status == "scheduled")
            .order_by(Match.queue_position.asc())
            .all()
        )
        for idx, match in enumerate(remaining, start=1):
            match.queue_position = idx

    affected_member_ids.discard(member_id)
    if affected_member_ids:
        sessions = (
            db.query(LoginSession)
            .filter(
                LoginSession.club_id == club_id,
                LoginSession.member_id.in_(list(affected_member_ids)),
                LoginSession.is_active.is_(True),
            )
            .all()
        )
        for s in sessions:
            s.is_in_match = False
            s.login_at = now
            s.wait_started_at = now

    db.query(LessonQueue).filter(
        LessonQueue.club_id == club_id,
        LessonQueue.member_id == member_id,
        LessonQueue.is_active.is_(True),
    ).update({LessonQueue.is_active: False}, synchronize_session=False)
    db.query(MatchRequest).filter(
        MatchRequest.club_id == club_id,
        MatchRequest.member_id == member_id,
        MatchRequest.day_date == today,
    ).delete(synchronize_session=False)


def get_default_club(db: Session) -> Club:
    club = db.query(Club).filter(Club.id == DEFAULT_CLUB_ID).first()
    if not club:
        club = Club(name="배드민턴 자동 매칭 시스템", login_title="출석")
        db.add(club)
        db.commit()
        db.refresh(club)
    return club


@router.get("/club", response_model=ClubOut)
def get_club(db: Session = Depends(get_db)):
    return get_default_club(db)


@router.patch("/club", response_model=ClubOut)
def update_club(payload: ClubUpdate, db: Session = Depends(get_db)):
    club = get_default_club(db)
    if payload.name is not None:
        club.name = payload.name
    if payload.login_title is not None:
        club.login_title = payload.login_title
    if payload.session_start_time is not None:
        club.session_start_time = payload.session_start_time
    if payload.session_end_time is not None:
        club.session_end_time = payload.session_end_time
    if payload.lesson_start_time is not None:
        club.lesson_start_time = payload.lesson_start_time
    if payload.match_duration_minutes is not None:
        club.match_duration_minutes = payload.match_duration_minutes
    db.commit()
    db.refresh(club)
    return club


@router.post("/admin/verify")
def verify_admin(payload: AdminVerify, db: Session = Depends(get_db)):
    club = get_default_club(db)
    if payload.code != club.admin_code:
        raise HTTPException(status_code=403, detail="관리자 코드가 올바르지 않습니다.")
    return {"ok": True}


@router.patch("/admin/code")
def update_admin_code(payload: AdminCodeUpdate, db: Session = Depends(get_db)):
    club = get_default_club(db)
    if payload.current_code != club.admin_code:
        raise HTTPException(status_code=403, detail="관리자 코드가 올바르지 않습니다.")
    club.admin_code = payload.new_code
    db.commit()
    return {"ok": True}


@router.post("/admin/reset-day")
def reset_day(db: Session = Depends(get_db)):
    club_id = DEFAULT_CLUB_ID
    now = datetime.utcnow()
    db.query(LoginSession).filter(LoginSession.club_id == club_id, LoginSession.is_active.is_(True)).update(
        {LoginSession.is_active: False, LoginSession.is_in_match: False, LoginSession.logout_at: now}
    )
    db.query(MatchParticipant).filter(
        MatchParticipant.day_date == date.today()
    ).delete()
    db.query(Match).filter(
        Match.club_id == club_id, Match.day_date == date.today()
    ).delete()
    db.query(LessonQueue).filter(LessonQueue.club_id == club_id, LessonQueue.is_active.is_(True)).update(
        {LessonQueue.is_active: False}
    )
    db.query(MatchRequest).filter(
        MatchRequest.club_id == club_id, MatchRequest.day_date == date.today()
    ).delete()
    day_session = ensure_day_session(db, club_id, date.today())
    day_session.first_login_at = None
    db.commit()
    return {"ok": True}


@router.patch("/admin/matches/{match_id}/teams")
def admin_update_match_teams(
    match_id: int, payload: AdminMatchTeamsUpdate, db: Session = Depends(get_db)
):
    """관리자 전용: 대기 경기(scheduled)의 선수를 대기자·다음경기 큐 인원으로 1명~4명 임의 수정합니다."""
    club_id = DEFAULT_CLUB_ID
    today = date.today()
    match = (
        db.query(Match)
        .filter(
            Match.id == match_id,
            Match.club_id == club_id,
            Match.day_date == today,
            Match.status == "scheduled",
        )
        .first()
    )
    if not match:
        raise HTTPException(status_code=404, detail="대기 중인 경기를 찾을 수 없습니다.")
    a_ids = payload.team_a_member_ids or []
    b_ids = payload.team_b_member_ids or []
    if len(a_ids) != 2 or len(b_ids) != 2:
        raise HTTPException(
            status_code=400,
            detail="팀 A 2명, 팀 B 2명으로 지정해주세요.",
        )
    all_four = list(a_ids) + list(b_ids)
    if len(set(all_four)) != 4:
        raise HTTPException(
            status_code=400,
            detail="4명 모두 서로 다른 회원으로 지정해주세요.",
        )
    active_sessions = (
        db.query(LoginSession)
        .filter(
            LoginSession.club_id == club_id,
            LoginSession.is_active.is_(True),
        )
        .all()
    )
    # 대기자 + 다음경기 큐 전원 (현재 경기 중인 사람만 제외)
    available_ids = {s.member_id for s in active_sessions if not s.is_in_match}
    for mid in all_four:
        if mid not in available_ids:
            raise HTTPException(
                status_code=400,
                detail="선수는 오늘 출석했으며 현재 경기 중이 아닌 회원이어야 합니다.(대기자 또는 다음경기 큐)",
            )
    members = db.query(Member).filter(Member.id.in_(all_four), Member.club_id == club_id).all()
    if len(members) != 4:
        raise HTTPException(status_code=400, detail="일부 회원을 찾을 수 없습니다.")

    old_a = [int(x) for x in match.team_a.split(",") if x]
    old_b = [int(x) for x in match.team_b.split(",") if x]
    if len(old_a) != 2 or len(old_b) != 2:
        old_a = old_a[:2] if len(old_a) >= 2 else old_a + [0] * (2 - len(old_a))
        old_b = old_b[:2] if len(old_b) >= 2 else old_b + [0] * (2 - len(old_b))
    old_four = old_a + old_b
    new_four = list(a_ids) + list(b_ids)

    scheduled_all = (
        db.query(Match)
        .filter(
            Match.club_id == club_id,
            Match.day_date == today,
            Match.status == "scheduled",
        )
        .all()
    )
    # 다음경기 풀에서 선택한 선수는 해당 경기와 교환(스왑): 코트/다음경기/대기자 풀에 같은 사람 중복 금지
    # (other_match_id, slot_index, replacement_member_id) 수집 후 일괄 적용
    swaps: list[tuple[Match, int, int]] = []
    for other_match in scheduled_all:
        if other_match.id == match.id:
            continue
        oa = [int(x) for x in other_match.team_a.split(",") if x]
        ob = [int(x) for x in other_match.team_b.split(",") if x]
        slots = (oa + ob)[:4]
        if len(slots) < 4:
            continue
        for i in range(4):
            if i >= len(new_four) or i >= len(old_four):
                continue
            if new_four[i] in slots:
                j = slots.index(new_four[i])
                swaps.append((other_match, j, old_four[i]))

    # 슬롯별로 한 명씩만 교체: (match, slot_idx, new_id). 같은 match의 같은 slot에 두 번 들어가면 나중 것만 적용
    by_match_slot: dict[tuple[int, int], int] = {}
    for other_match, j, replacement_id in swaps:
        by_match_slot[(other_match.id, j)] = replacement_id

    for other_match in scheduled_all:
        if other_match.id == match.id:
            continue
        oa = [int(x) for x in other_match.team_a.split(",") if x]
        ob = [int(x) for x in other_match.team_b.split(",") if x]
        slots = (oa + ob)[:4]
        if len(slots) < 4:
            continue
        for j in range(4):
            if (other_match.id, j) in by_match_slot:
                slots[j] = by_match_slot[(other_match.id, j)]
        other_match.team_a = ",".join(str(x) for x in slots[:2])
        other_match.team_b = ",".join(str(x) for x in slots[2:4])

    match.team_a = ",".join(str(x) for x in a_ids)
    match.team_b = ",".join(str(x) for x in b_ids)
    db.commit()
    return {"ok": True}


@router.post("/admin/force-logout/{member_id}")
def force_logout_member(member_id: int, db: Session = Depends(get_db)):
    session = (
        db.query(LoginSession)
        .filter(LoginSession.member_id == member_id, LoginSession.is_active.is_(True))
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="활성 세션이 없습니다.")
    session.is_active = False
    session.is_in_match = False
    session.logout_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/members", response_model=MemberOut)
def create_member(payload: MemberCreate, db: Session = Depends(get_db)):
    club = get_default_club(db)
    birth_year = _normalize_birth_year(payload.birth_year)
    if _member_exists(db, club.id, payload.name, birth_year):
        raise HTTPException(status_code=400, detail="동일한 이름과 생년(YY)의 회원이 이미 있습니다.")
    year = int(birth_year)
    full_year = 2000 + year if year <= 39 else 1900 + year
    rank_group = compute_rank_group(payload.local_grade, payload.national_grade, payload.is_player)
    points = assign_new_member_points(
        db, club.id, rank_group, payload.national_grade, payload.is_player
    )
    elo_seed = compute_seed_elo(payload.local_grade, payload.national_grade)
    birth_date = date(full_year, 1, 1)
    member = Member(
        club_id=club.id,
        name=payload.name,
        birth_date=birth_date,
        birth_year=birth_year,
        gender=payload.gender,
        local_grade=payload.local_grade,
        national_grade=payload.national_grade,
        is_player=payload.is_player,
        rank_group=rank_group,
        rating_points=points,
        elo_rating=elo_seed,
        win_streak=0,
    )
    db.add(member)
    db.flush()
    recalculate_ranks(db, club.id)
    db.commit()
    db.refresh(member)
    return member


@router.get("/members", response_model=list[MemberOut])
def list_members(db: Session = Depends(get_db)):
    club_id = DEFAULT_CLUB_ID
    active_ids = {
        row.member_id
        for row in db.query(LoginSession.member_id)
        .filter(LoginSession.club_id == club_id, LoginSession.is_active.is_(True))
        .all()
    }
    members = db.query(Member).filter(Member.club_id == club_id).all()
    for member in members:
        member.is_active = member.id in active_ids
    members.sort(
        key=lambda m: (0 if m.id in active_ids else 1, m.rank_position)
    )
    return members


@router.get("/public/ranking", response_model=list[PublicRankingItem])
def get_public_ranking(db: Session = Depends(get_db)):
    club_id = DEFAULT_CLUB_ID
    members = db.query(Member).filter(Member.club_id == club_id).all()
    active_ids = {
        row.member_id
        for row in db.query(LoginSession.member_id)
        .filter(LoginSession.club_id == club_id, LoginSession.is_active.is_(True))
        .all()
    }
    today = date.today()
    baseline_updated = False
    for member in members:
        if member.day_start_date != today:
            member.day_start_date = today
            member.day_start_rank_position = member.rank_position
            baseline_updated = True
        if member.last_rank_position is None:
            member.last_rank_position = member.rank_position
            baseline_updated = True
    if baseline_updated:
        db.commit()
    attendance_ids = {
        row.member_id
        for row in db.query(LoginSession.member_id)
        .filter(LoginSession.club_id == club_id, func.date(LoginSession.login_at) == today)
        .all()
    }
    attendance_time_map = {
        member_id: login_at
        for member_id, login_at in (
            db.query(LoginSession.member_id, func.min(LoginSession.login_at))
            .filter(LoginSession.club_id == club_id, func.date(LoginSession.login_at) == today)
            .group_by(LoginSession.member_id)
            .all()
        )
    }
    games_map = {
        member_id: count
        for member_id, count in (
            db.query(MatchParticipant.member_id, func.count(MatchParticipant.id))
            .filter(MatchParticipant.day_date == today)
            .group_by(MatchParticipant.member_id)
            .all()
        )
    }
    matches = (
        db.query(Match)
        .filter(Match.club_id == club_id, Match.day_date == today)
        .all()
    )
    match_counts = {member.id: {"MM": 0, "FF": 0, "MIX": 0} for member in members}
    if matches:
        member_map = {member.id: member for member in members}
        for match in matches:
            ids = [int(x) for x in (match.team_a + "," + match.team_b).split(",") if x]
            match_members = [member_map[mid] for mid in ids if mid in member_map]
            if not match_members:
                continue
            genders = {m.gender for m in match_members}
            if genders == {"M"}:
                match_type = "MM"
            elif genders == {"F"}:
                match_type = "FF"
            else:
                match_type = "MIX"
            for m in match_members:
                match_counts[m.id][match_type] += 1
    members.sort(key=lambda m: (0 if m.id in active_ids else 1, m.rank_position))
    return [
        PublicRankingItem(
            rank_position=member.rank_position,
            name=member.name,
            birth_year=member.birth_year,
            local_grade=member.local_grade,
            national_grade=member.national_grade,
            gender=member.gender,
            is_active=member.id in active_ids,
            games_today=games_map.get(member.id, 0),
            match_mm=match_counts.get(member.id, {}).get("MM", 0),
            match_ff=match_counts.get(member.id, {}).get("FF", 0),
            match_mix=match_counts.get(member.id, {}).get("MIX", 0),
            rank_delta=(member.last_rank_position or member.rank_position) - member.rank_position,
            attended_today=member.id in attendance_ids,
            attendance_time=attendance_time_map.get(member.id),
        )
        for member in members
    ]


@router.delete("/members/{member_id}")
def delete_member(member_id: int, db: Session = Depends(get_db)):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="회원이 없습니다.")
    club_id = member.club_id
    db.query(LoginSession).filter(LoginSession.member_id == member_id).delete()
    db.query(LessonQueue).filter(LessonQueue.member_id == member_id).delete()
    db.query(MatchParticipant).filter(MatchParticipant.member_id == member_id).delete()
    db.delete(member)
    recalculate_ranks(db, club_id)
    db.commit()
    return {"ok": True}


@router.patch("/members/{member_id}", response_model=MemberOut)
def update_member(member_id: int, payload: MemberUpdate, db: Session = Depends(get_db)):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="회원이 없습니다.")
    grade_changed = False
    next_name = payload.name if payload.name is not None else member.name
    next_birth = member.birth_year
    if payload.name is not None:
        member.name = payload.name
    if payload.birth_year is not None:
        birth_year = _normalize_birth_year(payload.birth_year)
        year = int(birth_year)
        full_year = 2000 + year if year <= 39 else 1900 + year
        member.birth_year = birth_year
        member.birth_date = date(full_year, 1, 1)
        next_birth = birth_year
    if _member_exists(db, member.club_id, next_name, next_birth, exclude_member_id=member.id):
        raise HTTPException(status_code=400, detail="동일한 이름과 생년(YY)의 회원이 이미 있습니다.")
    if payload.gender is not None:
        member.gender = payload.gender
    if payload.local_grade is not None:
        member.local_grade = payload.local_grade
        grade_changed = True
    if payload.national_grade is not None:
        member.national_grade = payload.national_grade
        grade_changed = True
    if payload.is_player is not None:
        member.is_player = payload.is_player
        grade_changed = True
    if grade_changed:
        member.rank_group = compute_rank_group(
            member.local_grade, member.national_grade, member.is_player
        )
        member.rating_points = assign_new_member_points(
            db, member.club_id, member.rank_group, member.national_grade, member.is_player
        )
        member.elo_rating = compute_seed_elo(member.local_grade, member.national_grade)
        member.win_streak = 0
        member.last_match_at = None
    recalculate_ranks(db, member.club_id)
    db.commit()
    db.refresh(member)
    return member


@router.patch("/members/by-identity", response_model=MemberOut)
def update_member_by_identity(payload: MemberUpdateByIdentity, db: Session = Depends(get_db)):
    birth_year = _normalize_birth_year(payload.birth_year)
    member = (
        db.query(Member)
        .filter(
            Member.club_id == DEFAULT_CLUB_ID,
            Member.name == payload.name,
            Member.birth_year == birth_year,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="회원이 없습니다.")
    grade_changed = False
    if payload.local_grade is not None:
        member.local_grade = payload.local_grade
        grade_changed = True
    if payload.national_grade is not None:
        member.national_grade = payload.national_grade
        grade_changed = True
    if payload.is_player is not None:
        member.is_player = payload.is_player
        grade_changed = True
    if grade_changed:
        member.rank_group = compute_rank_group(
            member.local_grade, member.national_grade, member.is_player
        )
        member.rating_points = assign_new_member_points(
            db, member.club_id, member.rank_group, member.national_grade, member.is_player
        )
        member.elo_rating = compute_seed_elo(member.local_grade, member.national_grade)
        member.win_streak = 0
        member.last_match_at = None
    recalculate_ranks(db, member.club_id)
    db.commit()
    db.refresh(member)
    return member


@router.patch("/members/{member_id}/grade", response_model=MemberOut)
def update_member_grade(member_id: int, payload: MemberUpdateGrade, db: Session = Depends(get_db)):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="회원이 없습니다.")
    if payload.local_grade is not None:
        member.local_grade = payload.local_grade
    if payload.national_grade is not None:
        member.national_grade = payload.national_grade
    if payload.is_player is not None:
        member.is_player = payload.is_player
    member.rank_group = compute_rank_group(member.local_grade, member.national_grade, member.is_player)
    member.rating_points = assign_new_member_points(
        db, member.club_id, member.rank_group, member.national_grade, member.is_player
    )
    member.elo_rating = compute_seed_elo(member.local_grade, member.national_grade)
    member.win_streak = 0
    member.last_match_at = None
    recalculate_ranks(db, member.club_id)
    db.commit()
    db.refresh(member)
    return member


@router.post("/auth/login", response_model=LoginSessionOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    _cleanup_stale_sessions(db, DEFAULT_CLUB_ID, date.today())
    birth_year = _normalize_birth_year(payload.birth_year)
    member = (
        db.query(Member)
        .filter(
            Member.club_id == DEFAULT_CLUB_ID,
            Member.name == payload.name,
            Member.birth_year == birth_year,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="회원정보가 없습니다.")
    existing = (
        db.query(LoginSession)
        .filter(LoginSession.member_id == member.id, LoginSession.is_active.is_(True))
        .first()
    )
    if existing:
        return existing
    now = datetime.now()
    session = LoginSession(
        club_id=DEFAULT_CLUB_ID,
        member_id=member.id,
        login_at=now,
        wait_started_at=now,
        is_active=True,
        is_guest=payload.is_guest,
    )
    db.add(session)
    today = date.today()
    if member.day_start_date != today:
        member.day_start_date = today
        member.day_start_rank_position = member.rank_position
    day_session = ensure_day_session(db, DEFAULT_CLUB_ID, date.today())
    if not day_session.first_login_at:
        day_session.first_login_at = session.login_at
    db.commit()
    db.refresh(session)
    return session


@router.post("/auth/logout")
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    session = db.query(LoginSession).filter(LoginSession.id == payload.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션이 없습니다.")
    club_id = session.club_id
    member_id = session.member_id
    session.is_active = False
    session.logout_at = datetime.utcnow()
    session.is_in_match = False
    _remove_member_from_today_flow(db, club_id, member_id, date.today())
    db.commit()
    return {"ok": True}


@router.post("/lessons")
def add_lesson_member(payload: LessonQueueItemCreate, db: Session = Depends(get_db)):
    club_id = DEFAULT_CLUB_ID
    exists = (
        db.query(LessonQueue)
        .filter(
            LessonQueue.club_id == club_id,
            LessonQueue.member_id == payload.member_id,
            LessonQueue.is_active.is_(True),
        )
        .first()
    )
    if exists:
        return {"ok": True, "skipped": True}
    last = (
        db.query(LessonQueue)
        .filter(LessonQueue.club_id == club_id, LessonQueue.is_active.is_(True))
        .order_by(LessonQueue.order_index.desc())
        .first()
    )
    order_index = 1 if not last else last.order_index + 1
    entry = LessonQueue(
        club_id=club_id,
        member_id=payload.member_id,
        order_index=order_index,
        group_size=payload.group_size,
    )
    db.add(entry)
    db.commit()
    return {"ok": True}


@router.post("/match-requests")
def create_match_request(payload: MatchRequestCreate, db: Session = Depends(get_db)):
    club_id = DEFAULT_CLUB_ID
    member = db.query(Member).filter(Member.id == payload.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="회원이 없습니다.")
    requester_session = (
        db.query(LoginSession)
        .filter(LoginSession.member_id == payload.member_id, LoginSession.is_active.is_(True))
        .first()
    )
    if not requester_session:
        raise HTTPException(status_code=400, detail="오늘 출석한 회원만 희망 매치업을 등록할 수 있습니다.")
    today = date.today()
    exists = (
        db.query(MatchRequest)
        .filter(
            MatchRequest.club_id == club_id,
            MatchRequest.member_id == payload.member_id,
            MatchRequest.day_date == today,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="오늘 이미 희망 매치업을 등록했습니다.")
    target_id = None
    already_played = False
    involved_ids = {member.id}
    if payload.target_name:
        target = (
            db.query(Member)
            .filter(
                Member.club_id == club_id,
                Member.name == payload.target_name,
            )
            .first()
        )
        if not target:
            raise HTTPException(status_code=404, detail="희망 매치업 상대를 찾을 수 없습니다.")
        target_session = (
            db.query(LoginSession)
            .filter(LoginSession.member_id == target.id, LoginSession.is_active.is_(True))
            .first()
        )
        if not target_session:
            raise HTTPException(status_code=400, detail="오늘 출석한 회원만 희망 매치업에 포함될 수 있습니다.")
        target_id = target.id
        involved_ids.add(target.id)
        member_matches = (
            db.query(MatchParticipant.match_id)
            .filter(
                MatchParticipant.member_id == member.id,
                MatchParticipant.day_date == today,
            )
            .all()
        )
        target_matches = (
            db.query(MatchParticipant.match_id)
            .filter(
                MatchParticipant.member_id == target.id,
                MatchParticipant.day_date == today,
            )
            .all()
        )
        member_ids = {m.match_id for m in member_matches}
        target_ids = {m.match_id for m in target_matches}
        already_played = len(member_ids.intersection(target_ids)) > 0
    for opponent_name in [payload.opponent_team_1, payload.opponent_team_2]:
        if not opponent_name:
            continue
        opponent = (
            db.query(Member)
            .filter(Member.club_id == club_id, Member.name == opponent_name)
            .first()
        )
        if not opponent:
            raise HTTPException(status_code=404, detail="희망 상대팀을 찾을 수 없습니다.")
        opponent_session = (
            db.query(LoginSession)
            .filter(LoginSession.member_id == opponent.id, LoginSession.is_active.is_(True))
            .first()
        )
        if not opponent_session:
            raise HTTPException(status_code=400, detail="오늘 출석한 회원만 희망 매치업에 포함될 수 있습니다.")
        involved_ids.add(opponent.id)
    request = MatchRequest(
        club_id=club_id,
        member_id=payload.member_id,
        target_member_id=target_id,
        opponent_team_1=payload.opponent_team_1,
        opponent_team_2=payload.opponent_team_2,
        day_date=today,
        is_deprioritized=already_played,
    )
    db.add(request)
    db.commit()
    if already_played:
        return {"ok": True, "message": "이미 오늘 경기한 매치입니다. 마지막 대기열로 이동합니다."}
    return {"ok": True}


@router.post("/lessons/reorder")
def reorder_lessons(payload: LessonQueueReorder, db: Session = Depends(get_db)):
    club_id = DEFAULT_CLUB_ID
    entries = (
        db.query(LessonQueue)
        .filter(LessonQueue.club_id == club_id, LessonQueue.is_active.is_(True))
        .all()
    )
    entry_map = {e.member_id: e for e in entries}
    for idx, member_id in enumerate(payload.ordered_member_ids, start=1):
        entry = entry_map.get(member_id)
        if entry:
            entry.order_index = idx
    db.commit()
    return {"ok": True}


@router.post("/matches/generate")
def generate_match_endpoint(db: Session = Depends(get_db)):
    club_id = DEFAULT_CLUB_ID
    now = datetime.utcnow()
    matches, next_candidates, waiting, lesson_lines = generate_matches(db, club_id, now)
    if not matches:
        return {
            "ok": True,
            "matches_created": 0,
            "waiting": waiting,
            "lesson_schedule": lesson_lines,
        }
    created = _create_matches(db, club_id, matches)
    return {"ok": True, "matches_created": created}


@router.post("/matches/finish")
def finish_match(payload: MatchFinishRequest, db: Session = Depends(get_db)):
    match = db.query(Match).filter(Match.id == payload.match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없습니다.")
    match.score_a = payload.score_a
    match.score_b = payload.score_b
    match.status = "completed"
    match.end_at = datetime.utcnow()
    team_a_ids = [int(x) for x in match.team_a.split(",") if x]
    team_b_ids = [int(x) for x in match.team_b.split(",") if x]
    members_a = db.query(Member).filter(Member.id.in_(team_a_ids)).all()
    members_b = db.query(Member).filter(Member.id.in_(team_b_ids)).all()
    apply_match_result(
        db,
        match.club_id,
        members_a,
        members_b,
        payload.score_a,
        payload.score_b,
        match.end_at,
    )
    sessions = (
        db.query(LoginSession)
        .filter(LoginSession.member_id.in_(team_a_ids + team_b_ids), LoginSession.is_active.is_(True))
        .all()
    )
    now = datetime.now()
    for session in sessions:
        session.is_in_match = False
        session.login_at = now
        session.wait_started_at = now
    db.commit()
    next_scheduled = (
        db.query(Match)
        .filter(
            Match.club_id == match.club_id,
            Match.day_date == now.date(),
            Match.status == "scheduled",
        )
        .order_by(Match.queue_position.asc())
        .first()
    )
    if next_scheduled:
        next_scheduled.status = "active"
        next_scheduled.start_at = now
        next_scheduled.court_number = match.court_number
        next_scheduled.queue_position = None
        team_a_ids = [int(x) for x in next_scheduled.team_a.split(",") if x]
        team_b_ids = [int(x) for x in next_scheduled.team_b.split(",") if x]
        for member_id in team_a_ids:
            db.add(
                MatchParticipant(
                    match_id=next_scheduled.id, member_id=member_id, team="A", day_date=next_scheduled.day_date
                )
            )
            session = (
                db.query(LoginSession)
                .filter(LoginSession.member_id == member_id, LoginSession.is_active.is_(True))
                .first()
            )
            if session:
                session.is_in_match = True
        for member_id in team_b_ids:
            db.add(
                MatchParticipant(
                    match_id=next_scheduled.id, member_id=member_id, team="B", day_date=next_scheduled.day_date
                )
            )
            session = (
                db.query(LoginSession)
                .filter(LoginSession.member_id == member_id, LoginSession.is_active.is_(True))
                .first()
            )
            if session:
                session.is_in_match = True
        db.query(Match).filter(
            Match.club_id == match.club_id,
            Match.day_date == now.date(),
            Match.status == "scheduled",
            Match.queue_position.isnot(None),
        ).update({Match.queue_position: Match.queue_position - 1})
        db.commit()

    # 큐 보충: 남은 scheduled가 3개 미만이면 추가 생성
    scheduled_matches = (
        db.query(Match)
        .filter(Match.club_id == match.club_id, Match.day_date == now.date(), Match.status == "scheduled")
        .order_by(Match.queue_position.asc())
        .all()
    )
    active_ids = _active_member_ids(db, match.club_id, now.date())
    scheduled_ids = {
        member_id
        for m in scheduled_matches
        for member_id in [int(x) for x in (m.team_a + "," + m.team_b).split(",") if x]
    }
    used_ids = active_ids | scheduled_ids
    while len(scheduled_matches) < 3:
        _, next_candidates, _, _ = generate_matches(
            db,
            match.club_id,
            now,
            court_numbers=[],
            exclude_member_ids=used_ids,
        )
        if not next_candidates:
            _, next_candidates, _, _ = generate_matches(
                db, match.club_id, now, court_numbers=[], exclude_member_ids=used_ids, force_create=True
            )
        if not next_candidates:
            break
        added = False
        for candidate in next_candidates:
            candidate_ids = {m.id for m in (candidate.team_a + candidate.team_b)}
            if candidate_ids.intersection(used_ids):
                continue
            scheduled = Match(
                club_id=match.club_id,
                day_date=now.date(),
                status="scheduled",
                queue_position=len(scheduled_matches) + 1,
                team_a=",".join(str(m.id) for m in candidate.team_a),
                team_b=",".join(str(m.id) for m in candidate.team_b),
            )
            db.add(scheduled)
            db.flush()
            scheduled_matches.append(scheduled)
            used_ids |= candidate_ids
            added = True
            break
        if not added:
            break
    db.commit()
    return {"ok": True}


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db)):
    club_id = DEFAULT_CLUB_ID
    now = datetime.now()
    today = now.date()
    _cleanup_stale_sessions(db, club_id, today)
    pending_sessions = (
        db.query(LoginSession)
        .filter(
            LoginSession.club_id == club_id,
            LoginSession.is_active.is_(False),
            func.date(LoginSession.login_at) == today,
            LoginSession.login_at <= now,
        )
        .all()
    )
    if pending_sessions:
        for session in pending_sessions:
            session.is_active = True
            session.is_in_match = False
            if not session.wait_started_at:
                session.wait_started_at = session.login_at
        db.commit()
    day_session = ensure_day_session(db, club_id, today)
    earliest_active = (
        db.query(LoginSession)
        .filter(LoginSession.club_id == club_id, LoginSession.is_active.is_(True))
        .order_by(LoginSession.login_at.asc())
        .first()
    )
    if earliest_active:
        if not day_session.first_login_at or day_session.first_login_at > earliest_active.login_at:
            day_session.first_login_at = earliest_active.login_at
            db.commit()
    club = get_default_club(db)
    active_matches = (
        db.query(Match)
        .filter(Match.club_id == club_id, Match.day_date == today, Match.status == "active")
        .order_by(Match.court_number.asc())
        .all()
    )
    scheduled_matches = (
        db.query(Match)
        .filter(Match.club_id == club_id, Match.day_date == today, Match.status == "scheduled")
        .order_by(Match.queue_position.asc())
        .all()
    )
    available_courts = _available_courts(db, club_id, today)
    if available_courts:
        if scheduled_matches:
            scheduled_queue = scheduled_matches[:]
            for court_number in available_courts:
                if not scheduled_queue:
                    break
                next_scheduled = scheduled_queue.pop(0)
                next_scheduled.status = "active"
                next_scheduled.start_at = now
                next_scheduled.court_number = court_number
                next_scheduled.queue_position = None
                team_a_ids = [int(x) for x in next_scheduled.team_a.split(",") if x]
                team_b_ids = [int(x) for x in next_scheduled.team_b.split(",") if x]
                for member_id in team_a_ids:
                    db.add(
                        MatchParticipant(
                            match_id=next_scheduled.id,
                            member_id=member_id,
                            team="A",
                            day_date=next_scheduled.day_date,
                        )
                    )
                    session = (
                        db.query(LoginSession)
                        .filter(LoginSession.member_id == member_id, LoginSession.is_active.is_(True))
                        .first()
                    )
                    if session:
                        session.is_in_match = True
                for member_id in team_b_ids:
                    db.add(
                        MatchParticipant(
                            match_id=next_scheduled.id,
                            member_id=member_id,
                            team="B",
                            day_date=next_scheduled.day_date,
                        )
                    )
                    session = (
                        db.query(LoginSession)
                        .filter(LoginSession.member_id == member_id, LoginSession.is_active.is_(True))
                        .first()
                    )
                    if session:
                        session.is_in_match = True
            # 재정렬
            remaining = (
                db.query(Match)
                .filter(Match.club_id == club_id, Match.day_date == today, Match.status == "scheduled")
                .order_by(Match.queue_position.asc())
                .all()
            )
            for idx, match in enumerate(remaining, start=1):
                match.queue_position = idx
            db.commit()
        else:
            matches, _, _, _ = generate_matches(db, club_id, now, court_numbers=available_courts)
            if not matches and available_courts:
                matches, _, _, _ = generate_matches(
                    db, club_id, now, court_numbers=available_courts, force_create=True
                )
            _create_matches(db, club_id, matches)
        active_matches = (
            db.query(Match)
            .filter(Match.club_id == club_id, Match.day_date == today, Match.status == "active")
            .order_by(Match.court_number.asc())
            .all()
        )
    courts: list[CourtDisplay] = []
    for match in active_matches:
        team_a_ids = [int(x) for x in match.team_a.split(",") if x]
        team_b_ids = [int(x) for x in match.team_b.split(",") if x]
        team_a_members = db.query(Member).filter(Member.id.in_(team_a_ids)).all()
        team_b_members = db.query(Member).filter(Member.id.in_(team_b_ids)).all()
        team_a_map = {m.id: m for m in team_a_members}
        team_b_map = {m.id: m for m in team_b_members}
        team_a = [team_a_map[mid] for mid in team_a_ids if mid in team_a_map]
        team_b = [team_b_map[mid] for mid in team_b_ids if mid in team_b_map]
        courts.append(
            CourtDisplay(
                court_number=match.court_number or 0,
                match_id=match.id,
                start_at=match.start_at,
                team_a=[format_member_label(m) for m in team_a],
                team_b=[format_member_label(m) for m in team_b],
                team_a_ids=team_a_ids,
                team_b_ids=team_b_ids,
                team_a_genders=[m.gender for m in team_a],
                team_b_genders=[m.gender for m in team_b],
            )
        )
    sessions = (
        db.query(LoginSession, Member)
        .join(Member, LoginSession.member_id == Member.id)
        .filter(LoginSession.club_id == club_id, LoginSession.is_active.is_(True))
        .order_by(LoginSession.login_at.asc())
        .all()
    )
    total_logged_in = len(sessions)
    in_match_count = sum(1 for session, _ in sessions if session.is_in_match)
    lesson_ids: set[int] = set()
    lesson_count = 0
    scheduled_matches = (
        db.query(Match)
        .filter(Match.club_id == club_id, Match.day_date == today, Match.status == "scheduled")
        .order_by(Match.queue_position.asc())
        .all()
    )
    if len(scheduled_matches) < 3:
        active_ids = _active_member_ids(db, club_id, today)
        kept_matches: list[Match] = []
        kept_ids: set[int] = set()

        def team_type(members: list[Member]) -> str:
            males = sum(1 for m in members if m.gender == "M")
            females = sum(1 for m in members if m.gender == "F")
            if males == 2:
                return "MM"
            if females == 2:
                return "FF"
            return "MIX"

        for match in scheduled_matches:
            team_a_ids = [int(x) for x in match.team_a.split(",") if x]
            team_b_ids = [int(x) for x in match.team_b.split(",") if x]
            members = db.query(Member).filter(Member.id.in_(team_a_ids + team_b_ids)).all()
            member_map = {m.id: m for m in members}
            team_a = [member_map[mid] for mid in team_a_ids if mid in member_map]
            team_b = [member_map[mid] for mid in team_b_ids if mid in member_map]
            if team_type(team_a) == team_type(team_b):
                kept_matches.append(match)
                kept_ids.update(team_a_ids + team_b_ids)
            else:
                db.delete(match)

        for idx, match in enumerate(kept_matches, start=1):
            match.queue_position = idx

        _, next_candidates, _, _ = generate_matches(
            db,
            club_id,
            now,
            court_numbers=[],
            exclude_member_ids=active_ids | kept_ids,
        )
        if not next_candidates:
            _, next_candidates, _, _ = generate_matches(
                db,
                club_id,
                now,
                court_numbers=[],
                exclude_member_ids=active_ids | kept_ids,
                force_create=True,
            )
        for candidate in next_candidates:
            scheduled = Match(
                club_id=club_id,
                day_date=today,
                status="scheduled",
                queue_position=len(kept_matches) + 1,
                team_a=",".join(str(m.id) for m in candidate.team_a),
                team_b=",".join(str(m.id) for m in candidate.team_b),
            )
            db.add(scheduled)
            kept_matches.append(scheduled)
            if len(kept_matches) >= 3:
                break
        db.commit()
    active_ids = _active_member_ids(db, club_id, today)
    scheduled_ids = {
        member_id
        for match in scheduled_matches
        for member_id in [int(x) for x in (match.team_a + "," + match.team_b).split(",") if x]
    }
    next_match_ids = scheduled_ids
    waiting_items = [
        WaitingItem(
            member_id=member.id,
            label=format_waiting_label(member),
            gender=member.gender,
            is_lesson=member.id in lesson_ids,
            wait_seconds=max(
                0,
                int((now - (session.wait_started_at or session.login_at)).total_seconds()),
            )
            if (session.wait_started_at or session.login_at)
            else 0,
        )
        for session, member in sessions
        if not session.is_in_match and member.id not in next_match_ids
    ]
    lesson_lines = []
    # 큐 보충은 finish_match에서 처리 (대시보드는 표시만)

    court_schedule = []
    for match in active_matches:
        base = match.start_at or now
        court_schedule.append(
            {
                "court": match.court_number or 0,
                "available_at": base + timedelta(minutes=15),
            }
        )
    court_schedule.sort(key=lambda item: item["available_at"])
    next_matches = []
    if scheduled_matches:
        for scheduled in scheduled_matches:
            team_a_ids = [int(x) for x in scheduled.team_a.split(",") if x]
            team_b_ids = [int(x) for x in scheduled.team_b.split(",") if x]
            team_a_members = db.query(Member).filter(Member.id.in_(team_a_ids)).all()
            team_b_members = db.query(Member).filter(Member.id.in_(team_b_ids)).all()
            team_a_map = {m.id: m for m in team_a_members}
            team_b_map = {m.id: m for m in team_b_members}
            team_a = [team_a_map[mid] for mid in team_a_ids if mid in team_a_map]
            team_b = [team_b_map[mid] for mid in team_b_ids if mid in team_b_map]
            expected_court = None
            expected_start_at = None
            if court_schedule:
                court_schedule.sort(key=lambda item: item["available_at"])
                slot = court_schedule[0]
                expected_court = slot["court"] or None
                expected_start_at = slot["available_at"]
                slot["available_at"] = slot["available_at"] + timedelta(minutes=15)
            next_matches.append(
                TeamDisplay(
                    match_id=scheduled.id,
                    team_a=[format_member_label(m) for m in team_a],
                    team_b=[format_member_label(m) for m in team_b],
                    team_a_ids=team_a_ids,
                    team_b_ids=team_b_ids,
                    team_a_genders=[m.gender for m in team_a],
                    team_b_genders=[m.gender for m in team_b],
                    expected_court=expected_court,
                    expected_start_at=expected_start_at,
                )
            )
    else:
        next_matches = []
    return DashboardOut(
        date_label=now.strftime("%m월 %d일"),
        club_name=club.name,
        courts=courts,
        next_matches=next_matches,
        waiting=waiting_items,
        lesson_schedule=lesson_lines,
        total_logged_in=total_logged_in,
        in_match_count=in_match_count,
        lesson_count=lesson_count,
        waiting_count=len(waiting_items),
    )
