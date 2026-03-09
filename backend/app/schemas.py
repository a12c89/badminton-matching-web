from datetime import date, datetime, time
from typing import List, Optional
from pydantic import BaseModel


class ClubUpdate(BaseModel):
    name: Optional[str] = None
    login_title: Optional[str] = None
    session_start_time: Optional[time] = None
    session_end_time: Optional[time] = None
    lesson_start_time: Optional[time] = None
    match_duration_minutes: Optional[int] = None


class ClubOut(BaseModel):
    id: int
    name: str
    login_title: str
    session_start_time: time
    session_end_time: time
    lesson_start_time: time
    match_duration_minutes: int

    class Config:
        from_attributes = True


class MemberCreate(BaseModel):
    name: str
    birth_year: str
    gender: str
    local_grade: Optional[str] = None
    national_grade: Optional[str] = None
    is_player: bool = False


class MemberUpdateGrade(BaseModel):
    local_grade: Optional[str] = None
    national_grade: Optional[str] = None
    is_player: Optional[bool] = None


class MemberUpdate(BaseModel):
    name: Optional[str] = None
    birth_year: Optional[str] = None
    gender: Optional[str] = None
    local_grade: Optional[str] = None
    national_grade: Optional[str] = None
    is_player: Optional[bool] = None


class MemberUpdateByIdentity(BaseModel):
    name: str
    birth_year: str
    local_grade: Optional[str] = None
    national_grade: Optional[str] = None
    is_player: Optional[bool] = None


class MemberOut(BaseModel):
    id: int
    club_id: int
    name: str
    birth_year: str
    gender: str
    local_grade: Optional[str]
    national_grade: Optional[str]
    is_player: bool
    rank_group: str
    rating_points: int
    rank_position: int
    is_active: Optional[bool] = None

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    name: str
    birth_year: str
    is_guest: bool = False


class LoginSessionOut(BaseModel):
    id: int
    member_id: int
    login_at: datetime
    is_active: bool
    is_guest: bool

    class Config:
        from_attributes = True


class LogoutRequest(BaseModel):
    session_id: int


class LessonQueueItemCreate(BaseModel):
    member_id: int
    group_size: int = 1


class LessonQueueReorder(BaseModel):
    ordered_member_ids: List[int]


class AdminVerify(BaseModel):
    code: str


class AdminCodeUpdate(BaseModel):
    current_code: str
    new_code: str


class MatchFinishRequest(BaseModel):
    match_id: int
    score_a: int
    score_b: int


class MatchRequestCreate(BaseModel):
    member_id: int
    target_name: Optional[str] = None
    opponent_team_1: Optional[str] = None
    opponent_team_2: Optional[str] = None


class PublicRankingItem(BaseModel):
    rank_position: int
    name: str
    birth_year: str
    local_grade: Optional[str] = None
    national_grade: Optional[str] = None
    gender: Optional[str] = None
    is_active: Optional[bool] = None
    games_today: int = 0
    match_mm: int = 0
    match_ff: int = 0
    match_mix: int = 0
    rank_delta: int = 0
    attended_today: bool = False
    attendance_time: Optional[datetime] = None


class TeamDisplay(BaseModel):
    match_id: Optional[int] = None
    team_a: List[str]
    team_b: List[str]
    team_a_ids: List[int] = []
    team_b_ids: List[int] = []
    team_a_genders: List[str] = []
    team_b_genders: List[str] = []
    expected_court: Optional[int] = None
    expected_start_at: Optional[datetime] = None


class WaitingItem(BaseModel):
    member_id: int = 0
    label: str
    gender: Optional[str] = None
    is_lesson: bool = False
    wait_seconds: int = 0


class AdminMatchTeamsUpdate(BaseModel):
    team_a_member_ids: List[int]
    team_b_member_ids: List[int]


class CourtDisplay(BaseModel):
    court_number: int
    match_id: int
    start_at: Optional[datetime] = None
    team_a: List[str]
    team_b: List[str]
    team_a_ids: List[int]
    team_b_ids: List[int]
    team_a_genders: List[str] = []
    team_b_genders: List[str] = []


class DashboardOut(BaseModel):
    date_label: str
    club_name: str
    courts: List[CourtDisplay]
    next_matches: List[TeamDisplay]
    waiting: List[WaitingItem]
    lesson_schedule: List[str]
    total_logged_in: int
    in_match_count: int
    lesson_count: int
    waiting_count: int
