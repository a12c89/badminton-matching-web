import { useEffect, useMemo, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "./api/client";

type Club = {
  id: number;
  name: string;
  login_title: string;
};

type Member = {
  id: number;
  name: string;
  birth_year: string;
  gender: string;
  local_grade?: string | null;
  national_grade?: string | null;
  is_player: boolean;
  rank_group: string;
  rank_position: number;
  is_active?: boolean;
};

type Dashboard = {
  date_label: string;
  club_name: string;
  courts: {
    court_number: number;
    match_id: number;
    team_a: string[];
    team_b: string[];
    team_a_ids: number[];
    team_b_ids: number[];
    team_a_genders: string[];
    team_b_genders: string[];
  }[];
  next_matches: {
    match_id?: number | null;
    team_a: string[];
    team_b: string[];
    team_a_ids?: number[];
    team_b_ids?: number[];
    team_a_genders: string[];
    team_b_genders: string[];
    expected_court?: number | null;
    expected_start_at?: string | null;
  }[];
  waiting: {
    member_id: number;
    label: string;
    gender?: string | null;
    is_lesson?: boolean;
    wait_seconds?: number;
  }[];
  lesson_schedule: string[];
  total_logged_in: number;
  in_match_count: number;
  lesson_count: number;
  waiting_count: number;
};

type View = "login" | "signup" | "dashboard" | "admin" | "lessons" | "ranking";

export default function App() {
  const [view, setView] = useState<View>("login");
  const [clubName, setClubName] = useState("");
  const [loginTitle, setLoginTitle] = useState("");
  const [memberName, setMemberName] = useState("");
  const [birthInput, setBirthInput] = useState("");
  const [gender, setGender] = useState("M");
  const [localGrade, setLocalGrade] = useState("C");
  const [nationalGrade, setNationalGrade] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [memberId, setMemberId] = useState<number | null>(null);
  const [isAdminSession, setIsAdminSession] = useState(false);
  const [isLessonLogin, setIsLessonLogin] = useState(false);
  const [lessonGroupSize, setLessonGroupSize] = useState(1);
  const [adminMode, setAdminMode] = useState(false);
  const [adminCode, setAdminCode] = useState("");
  const [adminCodeCurrent, setAdminCodeCurrent] = useState("");
  const [adminCodeNew, setAdminCodeNew] = useState("");
  const [members, setMembers] = useState<Member[]>([]);
  const [lessonOrderInput, setLessonOrderInput] = useState("");
  const [memberEdits, setMemberEdits] = useState<Record<number, Member>>({});
  const [birthEdits, setBirthEdits] = useState<Record<number, string>>({});
  const [memberSearch, setMemberSearch] = useState("");
  const [scoreInputs, setScoreInputs] = useState<Record<number, { a: string; b: string }>>({});
  const [lastRefreshAt, setLastRefreshAt] = useState("");
  const [requestTargetName, setRequestTargetName] = useState("");
  const [requestOpponent1, setRequestOpponent1] = useState("");
  const [requestOpponent2, setRequestOpponent2] = useState("");
  const [editMatchId, setEditMatchId] = useState<number | null>(null);
  const [editTeamA, setEditTeamA] = useState<[number, number]>([0, 0]);
  const [editTeamB, setEditTeamB] = useState<[number, number]>([0, 0]);
  const [rankings, setRankings] = useState<
    {
      rank_position: number;
      name: string;
      birth_year: string;
      local_grade?: string | null;
      national_grade?: string | null;
      gender?: string | null;
      is_active?: boolean;
      match_mm?: number;
      match_ff?: number;
      match_mix?: number;
      rank_delta?: number;
      attended_today?: boolean;
      attendance_time?: string | null;
    }[]
  >([]);
  const [message, setMessage] = useState("");
  const clubId = 1;

  useEffect(() => {
    if (view === "dashboard") {
      refreshDashboard();
    }
    if (view === "admin") {
      refreshMembers();
      fetchClub();
      refreshDashboard();
    }
    if (view === "ranking") {
      refreshRankings();
    }
  }, [clubId, view]);

  useEffect(() => {
    fetchClub();
  }, []);

  const gradeOptions = useMemo(() => ["A", "B", "C", "D", "E"], []);
  const nationalOptions = useMemo(() => ["S", "A", "B", "C", "D", "E"], []);

  const parseBirthYear = () => {
    if (!/^\d{2}$/.test(birthInput)) {
      return null;
    }
    return birthInput;
  };

  const formatYY = (value?: string | null) => {
    if (!value) return "";
    return value.slice(0, 2);
  };

  const isValidYY = (value: string) => /^\d{2}$/.test(value);

  const rankingStats = useMemo(() => {
    const stats = {
      total: rankings.length,
      male: 0,
      female: 0,
      grades: { A: 0, B: 0, C: 0, D: 0, E: 0 },
      ages: { "20대": 0, "30대": 0, "40대": 0, "50대": 0, "60대": 0, "70대+": 0 },
      breakdown: {
        남: { total: 0, ages: {} as Record<string, Record<string, number>> },
        여: { total: 0, ages: {} as Record<string, Record<string, number>> },
      },
    };
    const currentYear = new Date().getFullYear();
    rankings.forEach((item) => {
      if (item.gender === "M") stats.male += 1;
      if (item.gender === "F") stats.female += 1;
      const grade = (item.local_grade || "E").toUpperCase() as keyof typeof stats.grades;
      if (stats.grades[grade] !== undefined) {
        stats.grades[grade] += 1;
      }
      const yy = Number(formatYY(item.birth_year));
      if (!Number.isNaN(yy)) {
        const fullYear = yy <= 39 ? 2000 + yy : 1900 + yy;
        const age = currentYear - fullYear;
        if (age >= 20 && age < 30) stats.ages["20대"] += 1;
        else if (age >= 30 && age < 40) stats.ages["30대"] += 1;
        else if (age >= 40 && age < 50) stats.ages["40대"] += 1;
        else if (age >= 50 && age < 60) stats.ages["50대"] += 1;
        else if (age >= 60 && age < 70) stats.ages["60대"] += 1;
        else if (age >= 70) stats.ages["70대+"] += 1;

        const genderKey = item.gender === "M" ? "남" : item.gender === "F" ? "여" : null;
        if (genderKey) {
          stats.breakdown[genderKey].total += 1;
          const ageBand =
            age >= 20 && age < 30
              ? "20대"
              : age >= 30 && age < 40
                ? "30대"
                : age >= 40 && age < 50
                  ? "40대"
                  : age >= 50 && age < 60
                    ? "50대"
                    : age >= 60 && age < 70
                      ? "60대"
                      : "70대+";
          if (!stats.breakdown[genderKey].ages[ageBand]) {
            stats.breakdown[genderKey].ages[ageBand] = { A: 0, B: 0, C: 0, D: 0, E: 0 };
          }
          stats.breakdown[genderKey].ages[ageBand][grade] += 1;
        }
      }
    });
    return stats;
  }, [rankings]);

  const parseApiError = (err: unknown) => {
    const raw = err instanceof Error ? err.message : String(err);
    try {
      const parsed = JSON.parse(raw);
      const detail = parsed?.detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (Array.isArray(detail) && detail.length) {
        const first = detail[0];
        if (typeof first?.msg === "string") {
          return first.msg;
        }
      }
    } catch {
      // ignore JSON parsing
    }
    return raw;
  };

  const formatTodayLabel = () => {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    return `${yyyy}년 ${mm}월 ${dd}일`;
  };

  const refreshDashboard = async () => {
    try {
      const data = await apiGet<Dashboard>(`/dashboard`);
      setDashboard(data);
      setClubName(data.club_name);
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, "0");
      const mm = String(now.getMinutes()).padStart(2, "0");
      const ss = String(now.getSeconds()).padStart(2, "0");
      setLastRefreshAt(`${hh}시 ${mm}분 ${ss}`);
    } catch (err) {
      console.error(err);
    }
  };

  const refreshMembers = async () => {
    try {
      const data = await apiGet<Member[]>(`/members`);
      setMembers(data);
      const edits: Record<number, Member> = {};
      const births: Record<number, string> = {};
      data.forEach((m) => {
        edits[m.id] = { ...m };
        births[m.id] = formatYY(m.birth_year);
      });
      setMemberEdits(edits);
      setBirthEdits(births);
    } catch (err) {
      console.error(err);
    }
  };

  const refreshRankings = async () => {
    try {
      const data = await apiGet<
        {
          rank_position: number;
          name: string;
          birth_year: string;
          local_grade?: string | null;
          national_grade?: string | null;
          gender?: string | null;
          is_active?: boolean;
          games_today?: number;
        }[]
      >(`/public/ranking`);
      setRankings(data);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchClub = async () => {
    setMessage("");
    try {
      const club = await apiGet<Club>("/club");
      setClubName(club.name);
      setLoginTitle(club.login_title || "출석");
    } catch (err) {
      setMessage(String(err));
    }
  };

  const updateClubTitle = async () => {
    setMessage("");
    try {
      const club = await apiPatch<Club>("/club", {
        name: clubName,
        login_title: loginTitle,
      });
      setClubName(club.name);
      setLoginTitle(club.login_title || "출석");
      setMessage("클럽 제목 변경 완료");
    } catch (err) {
      setMessage(String(err));
    }
  };

  const registerMember = async () => {
    setMessage("");
    try {
      if (!memberName.trim()) {
        setMessage("이름을 입력해주세요.");
        window.alert("이름을 입력해주세요.");
        return;
      }
      const birthYear = parseBirthYear();
      if (!birthYear) {
        setMessage("출생연도는 YY 형식으로 입력해주세요.");
        window.alert("출생연도는 YY 형식으로 입력해주세요.");
        return;
      }
      await apiPost<Member>("/members", {
        name: memberName,
        birth_year: birthYear,
        gender,
        local_grade: localGrade || null,
        national_grade: nationalGrade || null,
      });
      setMessage("회원 등록 완료");
      setView("login");
    } catch (err) {
      const detail = parseApiError(err);
      window.alert(`회원가입 실패: ${detail}`);
      setMessage(detail);
    }
  };

  const loginMember = async () => {
    setMessage("");
    try {
      if (!memberName.trim()) {
        setMessage("이름을 입력해주세요.");
        window.alert("이름을 입력해주세요.");
        return;
      }
      const birthYear = parseBirthYear();
      if (!birthYear) {
        setMessage("출생연도는 YY 형식으로 입력해주세요.");
        window.alert("출생연도는 YY 형식으로 입력해주세요.");
        return;
      }
      if (adminMode) {
        if (!adminCode.trim()) {
          setMessage("관리자 코드를 입력해주세요.");
          window.alert("관리자 코드를 입력해주세요.");
          return;
        }
        await apiPost("/admin/verify", { code: adminCode });
      }
      const session = await apiPost<{ id: number; member_id: number }>("/auth/login", {
        name: memberName,
        birth_year: birthYear,
        is_guest: false,
      });
      setSessionId(session.id);
      setMemberId(session.member_id);
      if (adminMode) {
        setIsAdminSession(true);
        setView("admin");
      } else {
        setIsAdminSession(false);
        setView("dashboard");
      }
      if (isLessonLogin) {
        await apiPost(`/lessons`, { member_id: session.member_id, group_size: lessonGroupSize });
      }
      await refreshDashboard();
      setMessage("로그인 완료");
    } catch (err) {
      const detail = parseApiError(err);
      if (detail.includes("회원정보가 없습니다")) {
        window.alert("회원정보가 없습니다. 회원가입 버튼을 눌러주세요.");
      } else if (detail.includes("관리자 코드")) {
        window.alert(`로그인 실패: ${detail}`);
      } else {
        window.alert(`로그인 실패: ${detail}`);
      }
      setMessage(detail);
    }
  };

  const logoutMember = async () => {
    if (!sessionId) {
      setView("login");
      return;
    }
    try {
      await apiPost("/auth/logout", { session_id: sessionId });
    } catch (err) {
      console.error(err);
    }
    setSessionId(null);
    setMemberId(null);
    setIsAdminSession(false);
    setView("login");
  };


  useEffect(() => {
    if (view !== "dashboard" && view !== "lessons" && view !== "admin") {
      return;
    }
    const timer = setInterval(() => {
      refreshDashboard();
    }, 1000);
    return () => clearInterval(timer);
  }, [view]);

  const finishMatch = async (matchId: number) => {
    const scores = scoreInputs[matchId] || { a: "", b: "" };
    setMessage("");
    try {
      await apiPost(`/matches/finish`, {
        match_id: Number(matchId),
        score_a: Number(scores.a),
        score_b: Number(scores.b),
      });
      setScoreInputs((prev) => ({ ...prev, [matchId]: { a: "", b: "" } }));
      await refreshDashboard();
    } catch (err) {
      setMessage(String(err));
    }
  };

  const formatExpectedTime = (value: string) => {
    const date = new Date(value);
    // 백엔드 시간이 UTC 기준이므로 KST(+9)로 보정
    const kst = new Date(date.getTime() + 9 * 60 * 60 * 1000);
    const hh = String(kst.getHours()).padStart(2, "0");
    const mm = String(kst.getMinutes()).padStart(2, "0");
    return `${hh}시 ${mm}분`;
  };

  const formatWaitTime = (seconds?: number) => {
    const total = Math.max(0, Math.floor(seconds ?? 0));
    const mm = String(Math.floor(total / 60)).padStart(2, "0");
    const ss = String(total % 60).padStart(2, "0");
    return `${mm}분 ${ss}초`;
  };

  const formatAttendanceTime = (value?: string | null) => {
    if (!value) return "";
    const date = new Date(value);
    const kst = new Date(date.getTime() + 9 * 60 * 60 * 1000);
    const hh = String(kst.getHours()).padStart(2, "0");
    const mm = String(kst.getMinutes()).padStart(2, "0");
    return `${hh}시 ${mm}분`;
  };

  const renderTeam = (names: string[], genders?: string[], ids?: number[]) => {
    const hasSelf = memberId ? ids?.includes(memberId) : false;
    const selfClass = hasSelf ? "self" : "";
    return (
      <div className="team-row">
        {names.map((name, idx) => (
          <span
            key={`${name}-${idx}`}
            className={`waiting-chip name-chip ${selfClass} ${
              genders?.[idx] === "M" ? "male" : genders?.[idx] === "F" ? "female" : "neutral"
            }`}
          >
            {name}
          </span>
        ))}
      </div>
    );
  };

  return (
    <main>
      <h1>{clubName || "배드민턴 자동 매칭 시스템"}</h1>
      {message && <p>{message}</p>}

      {view === "login" && (
        <div className="card">
          <h2>{`${formatTodayLabel()} ${loginTitle || "출석"}`}</h2>
          <div className="grid">
            <div>
              <label>이름</label>
              <input value={memberName} onChange={(e) => setMemberName(e.target.value)} />
            </div>
            <div>
              <label>출생연도 (YY)</label>
              <input
                value={birthInput}
                onChange={(e) => setBirthInput(e.target.value)}
                placeholder="예: 90"
                maxLength={2}
              />
            </div>
            <div>
              <label>옵션</label>
              <div className="row">
                <button
                  type="button"
                  className={`toggle ${isLessonLogin ? "active" : ""}`}
                  onClick={() => setIsLessonLogin((prev) => !prev)}
                >
                  🎯 레슨자
                </button>
                <button
                  type="button"
                  className={`toggle ${adminMode ? "active" : ""}`}
                  onClick={() => setAdminMode((prev) => !prev)}
                >
                  🔒 관리자
                </button>
              </div>
            </div>
            {isLessonLogin && (
              <div>
                <label>레슨 인원 수</label>
                <select
                  value={lessonGroupSize}
                  onChange={(e) => setLessonGroupSize(Number(e.target.value))}
                >
                  {[1, 2, 3, 4].map((size) => (
                    <option key={size} value={size}>
                      {size}명
                    </option>
                  ))}
                </select>
              </div>
            )}
            {adminMode && (
              <div>
                <label>관리자 코드</label>
                <input
                  type="password"
                  value={adminCode}
                  onChange={(e) => setAdminCode(e.target.value)}
                />
              </div>
            )}
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={loginMember}>로그인</button>
            <button className="secondary" onClick={() => setView("signup")}>
              회원가입
            </button>
          </div>
        </div>
      )}

      {view === "signup" && (
        <div className="card">
          <h2>회원가입</h2>
          <div className="grid">
            <div>
              <label>이름</label>
              <input value={memberName} onChange={(e) => setMemberName(e.target.value)} />
            </div>
            <div>
              <label>출생연도 (YY)</label>
              <input
                value={birthInput}
                onChange={(e) => setBirthInput(e.target.value)}
                placeholder="예: 90"
                maxLength={2}
              />
            </div>
            <div>
              <label>성별</label>
              <select value={gender} onChange={(e) => setGender(e.target.value)}>
                <option value="M">남</option>
                <option value="F">여</option>
              </select>
            </div>
            <div>
              <label>시/도/구 급수</label>
              <select value={localGrade} onChange={(e) => setLocalGrade(e.target.value)}>
                {gradeOptions.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label>전국 급수</label>
              <select value={nationalGrade} onChange={(e) => setNationalGrade(e.target.value)}>
                <option value="">없음</option>
                {nationalOptions.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={registerMember}>회원가입</button>
            <button className="secondary" onClick={() => setView("login")}>
              로그인으로
            </button>
          </div>
        </div>
      )}

      {view === "dashboard" && (
        <>
          <div className="card">
            <div className="row">
              <button className="secondary" onClick={refreshDashboard}>
                새로고침
              </button>
              <button className="secondary" onClick={() => setView("lessons")}>
                레슨 현황
              </button>
              <button className="secondary" onClick={() => setView("ranking")}>
                회원 리스트
              </button>
              {isAdminSession && (
                <button className="secondary" onClick={() => setView("admin")}>
                  관리자 페이지
                </button>
              )}
              <button className="secondary" onClick={logoutMember}>
                로그아웃
              </button>
            </div>
          </div>

          <div className="card">
            <h2>
              {dashboard?.date_label} 코트 현황
              {lastRefreshAt && (
                <span style={{ marginLeft: 8, fontSize: 14 }}>(새로고침: {lastRefreshAt})</span>
              )}
            </h2>
            {dashboard?.courts?.length ? (
              dashboard.courts.map((court) => (
                <div key={court.court_number}>
                  <div className="tag">{court.court_number}코트</div>
                  {renderTeam(court.team_a, court.team_a_genders, court.team_a_ids)} vs{" "}
                  {renderTeam(court.team_b, court.team_b_genders, court.team_b_ids)}
                  <div className="row" style={{ marginTop: 6 }}>
                    <input
                      placeholder="A 점수"
                      value={scoreInputs[court.match_id]?.a || ""}
                      onChange={(e) =>
                        setScoreInputs((prev) => ({
                          ...prev,
                          [court.match_id]: {
                            a: e.target.value,
                            b: prev[court.match_id]?.b || "",
                          },
                        }))
                      }
                    />
                    <input
                      placeholder="B 점수"
                      value={scoreInputs[court.match_id]?.b || ""}
                      onChange={(e) =>
                        setScoreInputs((prev) => ({
                          ...prev,
                          [court.match_id]: {
                            a: prev[court.match_id]?.a || "",
                            b: e.target.value,
                          },
                        }))
                      }
                    />
                    <button onClick={() => finishMatch(court.match_id)}>경기 종료</button>
                  </div>
                </div>
              ))
            ) : (
              <p>진행 중인 경기가 없습니다.</p>
            )}
            <h3>다음 경기</h3>
            {dashboard?.next_matches?.length ? (
              <div className="next-matches">
                {dashboard.next_matches.map((match, idx) => (
                  <div key={idx} className="next-match-row">
                    <div className="next-match-meta" style={{ display: "flex", flexWrap: "nowrap", alignItems: "center", gap: 6 }}>
                      <span className="section-meta">예상</span>
                      {typeof match.expected_court === "number" && (
                        <span className="tag">{match.expected_court}코트</span>
                      )}
                      {match.expected_start_at && (
                        <span className="tag time-tag">{formatExpectedTime(match.expected_start_at)}</span>
                      )}
                      {adminMode && match.match_id != null && (
                        <button
                          type="button"
                          className="secondary"
                          style={{ fontSize: "0.85rem", padding: "4px 10px", flexShrink: 0, flexGrow: 0, width: "auto", minWidth: "unset" }}
                          onClick={() => {
                            setEditMatchId(match.match_id ?? null);
                            setEditTeamA(match.team_a_ids?.length === 2 ? [match.team_a_ids[0], match.team_a_ids[1]] : [0, 0]);
                            setEditTeamB(match.team_b_ids?.length === 2 ? [match.team_b_ids[0], match.team_b_ids[1]] : [0, 0]);
                          }}
                        >
                          수정
                        </button>
                      )}
                    </div>
                    <div className="next-match-teams">
                      {renderTeam(match.team_a, match.team_a_genders)}
                      <span className="vs-text">vs</span>
                      {renderTeam(match.team_b, match.team_b_genders)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p>다음 경기가 없습니다.</p>
            )}
            {adminMode && editMatchId != null && (() => {
              const poolMap = new Map<number, string>();
              dashboard?.waiting?.forEach((w) => poolMap.set(w.member_id, w.label));
              dashboard?.next_matches?.forEach((m) => {
                m.team_a_ids?.forEach((id, i) => poolMap.set(id, m.team_a?.[i] ?? String(id)));
                m.team_b_ids?.forEach((id, i) => poolMap.set(id, m.team_b?.[i] ?? String(id)));
              });
              const pool = Array.from(poolMap.entries()).map(([id, label]) => ({ id, label }));
              const other = (slot: "a0" | "a1" | "b0" | "b1") => {
                const o: number[] = [];
                if (slot !== "a0") o.push(editTeamA[0]); if (slot !== "a1") o.push(editTeamA[1]);
                if (slot !== "b0") o.push(editTeamB[0]); if (slot !== "b1") o.push(editTeamB[1]);
                return o.filter(Boolean);
              };
              return (
                <div className="modal-overlay" style={{ marginTop: 12 }}>
                  <div className="card" style={{ maxWidth: 480 }}>
                    <h3>대기 경기 선수 수정</h3>
                    <p className="section-meta">대기자 또는 다음경기 큐 인원으로 1명만 바꿔도 됩니다. (현재 경기 중 제외)</p>
                    <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
                      <label>팀 A 1번</label>
                      <select
                        value={editTeamA[0] || ""}
                        onChange={(e) => setEditTeamA([Number(e.target.value) || 0, editTeamA[1]])}
                      >
                        {pool.map((p) => (
                          <option key={p.id} value={p.id} disabled={other("a0").includes(p.id)}>
                            {p.label}
                          </option>
                        ))}
                      </select>
                      <label>팀 A 2번</label>
                      <select
                        value={editTeamA[1] || ""}
                        onChange={(e) => setEditTeamA([editTeamA[0], Number(e.target.value) || 0])}
                      >
                        {pool.map((p) => (
                          <option key={p.id} value={p.id} disabled={other("a1").includes(p.id)}>
                            {p.label}
                          </option>
                        ))}
                      </select>
                      <label>팀 B 1번</label>
                      <select
                        value={editTeamB[0] || ""}
                        onChange={(e) => setEditTeamB([Number(e.target.value) || 0, editTeamB[1]])}
                      >
                        {pool.map((p) => (
                          <option key={p.id} value={p.id} disabled={other("b0").includes(p.id)}>
                            {p.label}
                          </option>
                        ))}
                      </select>
                      <label>팀 B 2번</label>
                      <select
                        value={editTeamB[1] || ""}
                        onChange={(e) => setEditTeamB([editTeamB[0], Number(e.target.value) || 0])}
                      >
                        {pool.map((p) => (
                          <option key={p.id} value={p.id} disabled={other("b1").includes(p.id)}>
                            {p.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="row" style={{ marginTop: 12, gap: 8 }}>
                      <button
                        type="button"
                        onClick={async () => {
                          if (!editMatchId) return;
                          const a1 = editTeamA[0] || 0;
                          const a2 = editTeamA[1] || 0;
                          const b1 = editTeamB[0] || 0;
                          const b2 = editTeamB[1] || 0;
                          const ids = [a1, a2, b1, b2];
                          if (new Set(ids).size !== 4 || ids.some((id) => !id)) {
                            setMessage("4명 모두 서로 다른 회원으로 선택해주세요.");
                            window.alert("4명 모두 서로 다른 회원으로 선택해주세요.");
                            return;
                          }
                          try {
                            await apiPatch(`/admin/matches/${editMatchId}/teams`, {
                              team_a_member_ids: [a1, a2],
                              team_b_member_ids: [b1, b2],
                            });
                            setMessage("대기 경기 선수 수정 완료");
                            setEditMatchId(null);
                            const d = await apiGet<Dashboard>("/dashboard");
                            setDashboard(d);
                          } catch (e) {
                            const msg = e instanceof Error ? e.message : "수정 실패";
                            setMessage(msg);
                            window.alert(msg);
                          }
                        }}
                      >
                        저장
                      </button>
                      <button type="button" className="secondary" onClick={() => setEditMatchId(null)}>
                        취소
                      </button>
                    </div>
                  </div>
                </div>
              );
            })()}
            <div className="section-header">
              <h3>대기자</h3>
              {dashboard && (
                <span className="section-meta">
                  현재 출석 총 {dashboard.total_logged_in}명
                </span>
              )}
            </div>
            {dashboard?.waiting?.length ? (
              <div className="waiting-list">
                {dashboard.waiting.map((item, idx) => {
                  const genderClass =
                    item.gender === "M" ? "male" : item.gender === "F" ? "female" : "neutral";
                  const lessonClass = item.is_lesson ? "lesson" : "";
                  return (
                    <span key={`${item.label}-${idx}`} className={`waiting-chip ${genderClass} ${lessonClass}`}>
                      {item.label} {formatWaitTime(item.wait_seconds)}
                    </span>
                  );
                })}
              </div>
            ) : (
              <p>대기자 없음</p>
            )}
          </div>

          <div className="card">
            <h3>희망 매치업 (하루 1회)</h3>
            <div className="grid">
              <div>
                <label>희망 파트너 이름</label>
                <input
                  value={requestTargetName}
                  onChange={(e) => setRequestTargetName(e.target.value)}
                />
              </div>
              <div>
                <label>희망 상대팀 1 이름</label>
                <input
                  value={requestOpponent1}
                  onChange={(e) => setRequestOpponent1(e.target.value)}
                />
              </div>
              <div>
                <label>희망 상대팀 2 이름</label>
                <input
                  value={requestOpponent2}
                  onChange={(e) => setRequestOpponent2(e.target.value)}
                />
              </div>
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <button
                onClick={async () => {
                  if (!memberId) {
                    setMessage("로그인 정보가 없습니다.");
                    return;
                  }
                  if (!requestTargetName && !requestOpponent1 && !requestOpponent2) {
                    setMessage("희망 매치업 이름을 하나 이상 입력해주세요.");
                    window.alert("희망 매치업 이름을 하나 이상 입력해주세요.");
                    return;
                  }
                  const payload: {
                    member_id: number;
                    target_name?: string;
                    opponent_team_1?: string;
                    opponent_team_2?: string;
                  } = { member_id: memberId };
                  if (requestTargetName) {
                    payload.target_name = requestTargetName;
                  }
                  if (requestOpponent1) {
                    payload.opponent_team_1 = requestOpponent1;
                  }
                  if (requestOpponent2) {
                    payload.opponent_team_2 = requestOpponent2;
                  }
                  try {
                    const res = await apiPost<{ message?: string }>("/match-requests", payload);
                    if (res?.message) {
                      window.alert(res.message);
                    }
                    setRequestTargetName("");
                    setRequestOpponent1("");
                    setRequestOpponent2("");
                    setMessage("희망 매치업 등록 완료 (후순위 반영)");
                  } catch (err) {
                    const detail = parseApiError(err);
                    window.alert(`희망 매치업 등록 실패: ${detail}`);
                    setMessage(detail);
                  }
                }}
              >
                등록
              </button>
            </div>
          </div>
        </>
      )}

      {view === "admin" && (
        <>
          <div className="card">
            <h2>관리자 도구</h2>
            <div className="row">
              <button className="secondary" onClick={() => setView("dashboard")}>
                대시보드로
              </button>
              <button
                className="secondary"
                onClick={async () => {
                  const ok = window.confirm("오늘 로그인/매칭 상태를 초기화할까요?");
                  if (!ok) return;
                  try {
                    await apiPost("/admin/reset-day", {});
                    await refreshDashboard();
                    setMessage("오늘 상태 초기화 완료");
                  } catch (err) {
                    const detail = parseApiError(err);
                    window.alert(`초기화 실패: ${detail}`);
                    setMessage(detail);
                  }
                }}
              >
                오늘 상태 초기화
              </button>
              <button className="secondary" onClick={logoutMember}>
                로그아웃
              </button>
            </div>
          </div>

          <div className="card">
            <h2>레슨 대기열 관리</h2>
            <div className="row" style={{ marginTop: 8 }}>
              <input
                placeholder="순서 변경: 3,7,2"
                value={lessonOrderInput}
                onChange={(e) => setLessonOrderInput(e.target.value)}
              />
              <button
                onClick={async () => {
                  const ordered = lessonOrderInput
                    .split(",")
                    .map((v) => Number(v.trim()))
                    .filter((v) => !Number.isNaN(v));
                  await apiPost(`/lessons/reorder`, {
                    ordered_member_ids: ordered,
                  });
                  await refreshDashboard();
                }}
              >
                순서 변경
              </button>
            </div>
            <div style={{ marginTop: 12 }}>
              <h3>레슨 순서 및 예상시간</h3>
              <ul>
                {dashboard?.lesson_schedule?.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          </div>

          <div className="card">
            <h2>클럽 제목 변경</h2>
            <div className="row">
              <input
                placeholder="클럽명"
                value={clubName}
                onChange={(e) => setClubName(e.target.value)}
              />
              <input
                placeholder="로그인 타이틀 (예: 출석)"
                value={loginTitle}
                onChange={(e) => setLoginTitle(e.target.value)}
              />
              <button onClick={updateClubTitle}>변경</button>
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <input
                placeholder="현재 관리자 코드"
                value={adminCodeCurrent}
                onChange={(e) => setAdminCodeCurrent(e.target.value)}
              />
              <input
                placeholder="새 관리자 코드"
                value={adminCodeNew}
                onChange={(e) => setAdminCodeNew(e.target.value)}
              />
              <button
                onClick={async () => {
                  try {
                    await apiPatch("/admin/code", {
                      current_code: adminCodeCurrent,
                      new_code: adminCodeNew,
                    });
                    setAdminCodeCurrent("");
                    setAdminCodeNew("");
                    setMessage("관리자 코드 변경 완료");
                  } catch (err) {
                    setMessage(String(err));
                  }
                }}
              >
                관리자 코드 변경
              </button>
            </div>
          </div>

          <div className="card">
            <h2>회원 리스트 (수정 가능)</h2>
            <div className="row" style={{ marginBottom: 8 }}>
              <button className="secondary" onClick={refreshMembers}>
                새로고침
              </button>
            </div>
            <div className="row" style={{ marginBottom: 12 }}>
              <input
                placeholder="회원 검색 (이름 또는 출생연도 YY)"
                value={memberSearch}
                onChange={(e) => setMemberSearch(e.target.value)}
              />
            </div>
            <div className="member-list">
            <div className="member-row header">
                <div>이름</div>
              <div>YY</div>
                <div>성별</div>
              <div>시/도/구</div>
              <div>전국</div>
                <div>저장</div>
              <div>출석</div>
                <div>삭제</div>
              </div>

              {members.length ? (
                <div>
                  {members
                    .filter((m) => {
                      if (!memberSearch) return true;
                      const needle = memberSearch.trim();
                      if (!needle) return true;
                      const birth = formatYY(m.birth_year);
                      return m.name.includes(needle) || birth.includes(needle);
                    })
                    .map((m) => {
                    const edit = memberEdits[m.id] || m;
                    return (
                      <div key={m.id} className="member-row">
                        <input
                          value={edit.name}
                          onChange={(e) =>
                            setMemberEdits((prev) => ({
                              ...prev,
                              [m.id]: { ...edit, name: e.target.value },
                            }))
                          }
                        />
                        <input
                          value={birthEdits[m.id] || ""}
                          onChange={(e) =>
                            setBirthEdits((prev) => ({
                              ...prev,
                              [m.id]: e.target.value,
                            }))
                          }
                          placeholder="YY"
                          maxLength={2}
                        />
                        <select
                          value={edit.gender}
                          onChange={(e) =>
                            setMemberEdits((prev) => ({
                              ...prev,
                              [m.id]: { ...edit, gender: e.target.value },
                            }))
                          }
                        >
                          <option value="M">남</option>
                          <option value="F">여</option>
                        </select>
                        <select
                          value={edit.local_grade || "E"}
                          onChange={(e) =>
                            setMemberEdits((prev) => ({
                              ...prev,
                              [m.id]: { ...edit, local_grade: e.target.value },
                            }))
                          }
                        >
                          {gradeOptions.map((g) => (
                            <option key={g} value={g}>
                              {g}
                            </option>
                          ))}
                        </select>
                        <select
                          value={edit.national_grade || ""}
                          onChange={(e) =>
                            setMemberEdits((prev) => ({
                              ...prev,
                              [m.id]: { ...edit, national_grade: e.target.value },
                            }))
                          }
                        >
                        <option value="">없음</option>
                        {nationalOptions.map((g) => (
                            <option key={g} value={g}>
                              {g}
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={async () => {
                            const birthYear = formatYY(birthEdits[m.id] || "");
                            if (!isValidYY(birthYear)) {
                              setMessage("출생연도는 YY 형식으로 입력해주세요.");
                              return;
                            }
                            await apiPatch(`/members/${m.id}`, {
                              name: edit.name,
                              birth_year: birthYear,
                              gender: edit.gender,
                              local_grade: edit.local_grade,
                              national_grade: edit.national_grade || null,
                            });
                            await refreshMembers();
                          }}
                        >
                          저장
                        </button>
                        <button
                          className={`attendance ${m.is_active ? "active" : "inactive"}`}
                          disabled={!m.is_active}
                          onClick={async () => {
                            try {
                              await apiPost(`/admin/force-logout/${m.id}`, {});
                              await refreshDashboard();
                              await refreshMembers();
                              setMessage("로그아웃 완료");
                            } catch (err) {
                              const detail = parseApiError(err);
                              window.alert(`로그아웃 실패: ${detail}`);
                              setMessage(detail);
                            }
                          }}
                        >
                          출석
                        </button>
                        <button
                          className="secondary"
                          onClick={async () => {
                            await apiDelete(`/members/${m.id}`);
                            await refreshMembers();
                          }}
                        >
                          삭제
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p>회원 없음</p>
              )}
            </div>
          </div>
        </>
      )}

      {view === "lessons" && (
        <>
          <div className="card">
            <h2>레슨 현황</h2>
            <div className="row">
              <button className="secondary" onClick={() => setView("dashboard")}>
                대시보드로
              </button>
              <button className="secondary" onClick={refreshDashboard}>
                새로고침
              </button>
            </div>
          </div>
          <div className="card">
            <h3>레슨 순서 및 예상시간</h3>
            <ul>
              {dashboard?.lesson_schedule?.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        </>
      )}

      {view === "ranking" && (
        <>
          <div className="card">
            <h2>회원 리스트</h2>
            <div className="row">
              <button className="secondary" onClick={() => setView("dashboard")}>
                대시보드로
              </button>
              <button className="secondary" onClick={refreshRankings}>
                새로고침
              </button>
            </div>
          </div>
          <div className="card">
            {rankings.length ? (
              <div className="ranking-list">
                {rankings.map((item) => {
                  const genderClass =
                    item.gender === "M" ? "male" : item.gender === "F" ? "female" : "neutral";
                  const rankDelta = item.rank_delta || 0;
                  const rankDeltaLabel =
                    rankDelta > 0 ? `▲${rankDelta}` : rankDelta < 0 ? `▼${Math.abs(rankDelta)}` : "";
                  const totalGames = (item.match_mm || 0) + (item.match_ff || 0) + (item.match_mix || 0);
                  const matchSummary = item.attended_today
                    ? item.gender === "M"
                      ? `남복 ${item.match_mm || 0} / 혼복 ${item.match_mix || 0} / 총 ${totalGames}게임`
                      : `여복 ${item.match_ff || 0} / 혼복 ${item.match_mix || 0} / 총 ${totalGames}게임`
                    : "";
                  return (
                    <div key={`${item.rank_position}-${item.name}`} className="ranking-row">
                      <span className={`waiting-chip ${genderClass} ${item.is_active ? "active" : "inactive"}`}>
                        <span className="attendance-dot" />
                        {String(item.rank_position).padStart(2, "0")}/{item.name}(
                        {formatYY(item.birth_year)})/{item.local_grade || "-"}/
                        {item.national_grade || "-"}
                        {matchSummary ? ` : ${matchSummary}` : ""}
                        {rankDeltaLabel ? (
                          <span className={`rank-delta ${rankDelta > 0 ? "up" : "down"}`}>
                            {rankDeltaLabel}
                          </span>
                        ) : null}
                      </span>
                    </div>
                  );
                })}
                <div className="ranking-summary">
                  <div className="summary-row">
                    회원 총 {rankingStats.total}명 : 남 {rankingStats.male}명, 여 {rankingStats.female}명
                  </div>
                  <div className="summary-table">
                    <table>
                      <thead>
                        <tr>
                          <th>성별</th>
                          <th>연령대</th>
                          <th>A조</th>
                          <th>B조</th>
                          <th>C조</th>
                          <th>D조</th>
                          <th>E조</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(["남", "여"] as const).map((gender) => {
                          const ageOrder = ["20대", "30대", "40대", "50대", "60대", "70대+"];
                          const ageRows = ageOrder
                            .filter((ageBand) => rankingStats.breakdown[gender].ages[ageBand])
                            .map((ageBand) => [ageBand, rankingStats.breakdown[gender].ages[ageBand]] as const);
                          if (!ageRows.length) {
                            return (
                              <tr key={gender}>
                                <td>{gender}</td>
                                <td colSpan={6}>데이터 없음</td>
                              </tr>
                            );
                          }
                          return ageRows.map(([ageBand, grades], idx) => (
                            <tr key={`${gender}-${ageBand}`}>
                              {idx === 0 && <td rowSpan={ageRows.length}>{gender}</td>}
                              <td>{ageBand}</td>
                              <td>{grades.A}</td>
                              <td>{grades.B}</td>
                              <td>{grades.C}</td>
                              <td>{grades.D}</td>
                              <td>{grades.E}</td>
                            </tr>
                          ));
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : (
              <p>순위 데이터가 없습니다.</p>
            )}
          </div>
        </>
      )}
    </main>
  );
}
