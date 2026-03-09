from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from ..models import Club, LessonQueue, Member


def get_lesson_schedule(
    db: Session, club_id: int, day_date: date
) -> List[Tuple[datetime, datetime, List[Member]]]:
    club = db.query(Club).filter(Club.id == club_id).first()
    if not club:
        return []
    queue = (
        db.query(LessonQueue, Member)
        .join(Member, LessonQueue.member_id == Member.id)
        .filter(LessonQueue.club_id == club_id, LessonQueue.is_active.is_(True))
        .order_by(LessonQueue.order_index.asc(), LessonQueue.created_at.asc())
        .all()
    )
    if not queue:
        return []

    start_time = datetime.combine(day_date, club.lesson_start_time)
    schedule: List[Tuple[datetime, datetime, List[Member]]] = []
    idx = 0
    while idx < len(queue):
        entry, member = queue[idx]
        group_size = max(1, min(4, entry.group_size))
        members = [member]
        for j in range(1, group_size):
            if idx + j < len(queue):
                members.append(queue[idx + j][1])
        duration = timedelta(minutes=group_size * 10)
        end_time = start_time + duration
        schedule.append((start_time, end_time, members))
        start_time = end_time
        idx += group_size
    return schedule


def build_lesson_display(
    schedule: List[Tuple[datetime, datetime, List[Member]]],
    now: datetime,
) -> List[str]:
    lines: List[str] = []
    for idx, (start_at, end_at, members) in enumerate(schedule, start=1):
        status = "예정"
        if start_at <= now <= end_at:
            status = "진행중"
        if now > end_at:
            status = "완료"
        names = " ".join([format_member_label(m) for m in members])
        lines.append(
            f"{idx:02d}. {start_at.strftime('%H:%M')}~{end_at.strftime('%H:%M')} : {names} ({status})"
        )
    return lines


def get_member_lesson_windows(
    schedule: List[Tuple[datetime, datetime, List[Member]]],
) -> Dict[int, Tuple[datetime, datetime]]:
    windows: Dict[int, Tuple[datetime, datetime]] = {}
    for start_at, end_at, members in schedule:
        window_start = start_at - timedelta(minutes=10)
        window_end = end_at + timedelta(minutes=5)
        for member in members:
            windows[member.id] = (window_start, window_end)
    return windows


def format_member_label(member: Member) -> str:
    seed = f"{member.rank_position:02d}" if member.rank_position < 100 else str(member.rank_position)
    return f"{seed}{member.name}"


def format_waiting_label(member: Member) -> str:
    return format_member_label(member)
