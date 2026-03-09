---
name: badminton-matching-web
overview: 웹(PWA) 기반 자동 대진 매칭 시스템을 무료 클라우드에 배포할 수 있도록 파이썬 백엔드와 웹 프론트를 설계/구현합니다.
todos:
  - id: scaffold-web
    content: FastAPI/React(PWA) 프로젝트 뼈대 생성
    status: completed
  - id: db-schema
    content: Postgres 스키마 및 ORM 모델 작성
    status: completed
  - id: matching-engine
    content: 매칭/레슨/랭킹 서비스 로직 구현
    status: completed
  - id: api-ui
    content: API 연결 및 대시보드 UI 구현
    status: completed
  - id: deploy
    content: 무료 클라우드 배포 및 접근 링크 제공
    status: completed
isProject: false
---

# 자동 대진 매칭 웹앱 계획

## 목표
- 링크 접속만으로 사용 가능한 웹(PWA) 기반 시스템
- 클럽 단위 회원/게스트 관리, 자동 대진 매칭, 레슨 스케줄/대기열, 결과 저장 및 등수 반영
- 무료 클라우드 배포(예: Render/Fly.io + Supabase/Postgres)

## 아키텍처 초안
- 백엔드: FastAPI (Python)
- DB: Postgres (Supabase 무료 플랜)
- 프론트: React + Vite (PWA)
- 배포: Render/Fly.io(백엔드) + Vercel/Netlify(프론트)

## 핵심 도메인 모델
- Club, Member, GuestSession, LoginSession
- RatingTier (S/A/B/C/D/E, 시/도/구 급수, 전국 급수)
- RankHistory, Match, Court, MatchQueue
- LessonQueue, LessonSlot

## 매칭 알고리즘 설계
- 입력: 로그인한 회원/게스트 + 레슨 제외 구간 + 최근 매칭 이력
- 제약: 3코트, 복식 4인, 남복/여복 우선, 혼복 후순위
- 목표: 급수/등수 격차 최소화 + 당일 재매칭 최소화 + 선착순 우선
- 로직 초안:
  - 후보 필터: 레슨 제외 시간대 제외
  - 그룹화: 성별, 급수(전국/지역) 우선 매칭
  - 스코어 함수: 급수/등수 차이, 최근 상대/팀 여부 패널티
  - 매칭 생성: 10분 대기 후 최적 조합 업데이트

## 화면/기능
- 회원가입/로그인(이름+생년월일)
- 클럽 운영자 화면(레슨 순서 조정)
- 오늘 코트 현황, 다음 경기, 대기자, 레슨 스케줄 표시

## 데이터 저장/랭킹
- 경기 종료 시 점수 기록
- 승급/급수 수정 가능
- 새 회원/게스트/급수 변경 시 최하 등수 부여 규칙 적용
- 랭킹 공개(시드 번호로 표시)

## 파일 구조(초안)
- Backend
  - [backend/app/main.py](backend/app/main.py)
  - [backend/app/models.py](backend/app/models.py)
  - [backend/app/schemas.py](backend/app/schemas.py)
  - [backend/app/services/matching.py](backend/app/services/matching.py)
  - [backend/app/services/lesson.py](backend/app/services/lesson.py)
  - [backend/app/services/ranking.py](backend/app/services/ranking.py)
  - [backend/app/api/routes.py](backend/app/api/routes.py)
- Frontend
  - [frontend/src/App.tsx](frontend/src/App.tsx)
  - [frontend/src/pages/Dashboard.tsx](frontend/src/pages/Dashboard.tsx)
  - [frontend/src/pages/Login.tsx](frontend/src/pages/Login.tsx)
  - [frontend/src/pages/AdminLessons.tsx](frontend/src/pages/AdminLessons.tsx)
  - [frontend/src/components/CourtBoard.tsx](frontend/src/components/CourtBoard.tsx)

## 배포 계획
- Supabase 프로젝트 생성 및 DB 스키마 적용
- Render/Fly.io에 FastAPI 배포
- Vercel/Netlify에 프론트 배포
- PWA 설정으로 홈화면 설치 지원

## 테스트/검증
- 매칭 결과 샘플 시나리오 테스트
- 레슨 제외 시간대/대기열 동작 확인
- 재매칭 방지 및 선착순 우선 로직 검증
