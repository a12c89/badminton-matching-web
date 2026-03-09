# 완전 무료 배포 가이드 (PC 꺼져도 접속 가능)

목표:
- 백엔드: Render (고정 도메인 제공)
- DB: Supabase Postgres (무료)
- 프론트: Vercel (고정 도메인 제공)

이 조합이면 링크가 매번 바뀌지 않고, PC를 꺼도 서비스가 유지됩니다.

---

## 1) Supabase Postgres 생성

1. [https://supabase.com](https://supabase.com)에서 새 프로젝트 생성
2. `Settings -> Database -> Connection string`에서 `URI` 복사
3. URI는 보통 아래 형태:

```env
postgresql://USER:PASSWORD@HOST:5432/postgres
```

---

## 2) GitHub에 코드 올리기

Render/Vercel은 GitHub 저장소 연결 방식이 가장 쉽습니다.

```bash
cd C:\Users\TaeWoo\Documents\badminton-matching-web
git init
git add .
git commit -m "deploy: initial"
```

이후 GitHub에서 빈 저장소를 만든 뒤 `git remote add origin ...` / `git push -u origin main` 실행.

---

## 3) Render에 백엔드 배포

1. [https://render.com](https://render.com) 로그인
2. `New + -> Web Service`
3. GitHub 저장소 선택
4. 설정:
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Environment Variables 추가:
   - `DATABASE_URL` = Supabase URI
   - `CORS_ORIGINS` = `https://<vercel-도메인>`
6. 배포 완료 후 백엔드 URL 확인:
   - 예: `https://badminton-api.onrender.com`

헬스체크:
- `https://<render-url>/api/club` 열어서 JSON 응답 확인

---

## 4) Vercel에 프론트 배포

1. [https://vercel.com](https://vercel.com) 로그인
2. `Add New -> Project`에서 같은 GitHub 저장소 선택
3. 설정:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Vite
4. Environment Variables:
   - `VITE_API_BASE` = `https://<render-url>/api`
5. Deploy

배포 완료 후:
- 예: `https://badminton-matching-web.vercel.app`

---

## 5) CORS 최종 마무리

Vercel 실제 도메인이 확정되면, Render 환경변수 `CORS_ORIGINS`를 정확히 갱신:

```env
CORS_ORIGINS=https://badminton-matching-web.vercel.app
```

필요 시 여러 도메인도 가능(콤마 구분):

```env
CORS_ORIGINS=https://badminton-matching-web.vercel.app,https://www.your-domain.com
```

---

## 6) 운영 시 참고

- Render Free는 오랫동안 요청이 없으면 sleep 상태가 될 수 있어 첫 접속이 느릴 수 있습니다.
- URL 자체는 고정되어 유지됩니다.
- 정말 항상 빠른 응답이 필요하면 유료 플랜이 필요합니다.
