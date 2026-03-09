---
name: ranking-elo-redesign
overview: 급수 기반 초기 점수 + Elo 업데이트 + 연승 지수 가중 + 30일 시간 감쇠를 적용한 새 등수 시스템을 설계하고 적용합니다.
todos:
  - id: design-elo-formula
    content: Elo/연승/감쇠 수식 확정 및 상수 결정
    status: completed
  - id: extend-models
    content: Member에 Elo/연승 필드 추가 및 마이그레이션
    status: completed
  - id: update-ranking
    content: 경기 종료 시 Elo 갱신 로직 구현
    status: completed
  - id: update-api-ui
    content: 등수/화살표 표시용 데이터 검증
    status: completed
isProject: false
---

# Elo 기반 등수 재설계

## 목표

- 급수로 초기 점수 설정
- 복식 경기 결과로 Elo 점수 실시간 갱신
- 연승 시 지수 가중 반영
- 오래된 전적은 30일 감쇠
- 현재 UI(등수 표시/화살표)와 호환

## 핵심 설계

- 초기 점수(Seed): `local_grade`와 `national_grade`를 점수화해 가중합으로 변환
- Elo 갱신: 팀 Elo(팀 평균)로 기대승률 계산 후 승/패 점수 업데이트
- 연승 가중: 개인의 연승 수에 따라 K값에 지수 배수 적용
- 시간 감쇠: 30일을 기준으로 오래된 경기의 영향도를 감소

## 변경 범위

- 점수 모델 및 업데이트 로직: [backend\app\services\ranking.py](backend\app\services\ranking.py)
- 연승/전적 저장용 필드 확장: [backend\app\models.py](backend\app\models.py)
- 스키마 마이그레이션: [backend\app\main.py](backend\app\main.py)
- 등수 표시 데이터 공급: [backend\app\api\routes.py](backend\app\api\routes.py)

## 구현 개요

- Elo 점수 필드(예: `elo_rating`) 추가
- 연승 카운트 필드(예: `win_streak`) 추가
- 경기 종료 시:
  - 각 팀 평균 Elo 계산
  - 기대 승률 계산
  - K값 = 기본 K × (연승 지수 가중)
  - 승/패 팀 개별 Elo 업데이트
  - 연승 갱신(승자 +1, 패자 0)
  - 시간 감쇠 반영(경기 시각 vs 현재 시각)
- `recalculate_ranks()`는 Elo 점수 기반 정렬로 교체

## 테스트/검증

- 더미 경기 결과로 Elo 상승/하락 확인
- 연승 시 상승폭 증가 확인
- 과거 경기 영향이 시간에 따라 감소하는지 확인
- UI 등수 화살표 동작 확인

