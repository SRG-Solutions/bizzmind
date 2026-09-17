# Bizzmind — деплой

## Услуги
| Компонент | Къде | Как |
|---|---|---|
| Supabase | Postgres + Auth + Storage | проект `knyznqohyvikesjtjdso` (eu-west-1); миграции в `supabase/migrations/` |
| API (FastAPI) | **Vercel** проект `bizzmind-api` (repo root: `api/index.py` + `vercel.json`) → https://bizzmind-api.vercel.app | env: Supabase, Gamma, AI_BACKEND=api, ANTHROPIC_API_KEY, COOKIE_SECURE=1, CRON_SECRET |
| Worker (AI задачи) | **Vercel функция**: клиентът вика `POST /api/jobs/{id}/run` веднага след enqueue (заявката тече докато задачата свърши, maxDuration); резерва: cron `/api/cron/jobs` | Hobby: 300 s и само дневен cron; Pro: до 800 s и cron всяка минута |
| Web (Next.js) | **Vercel** проект `bizzmind` (rootDirectory `web/`) → https://bizzmind-lac.vercel.app | env: `API_URL=https://bizzmind-api.vercel.app` |

## Env променливи (API и worker)
`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_DB_URL` (pooler 6543),
`ANTHROPIC_API_KEY` + `AI_BACKEND=api` (продукция), `GAMMA_API_KEY`, `COOKIE_SECURE=1`.

## Vercel — как е вързано
- И двата проекта са свързани с GitHub `SRG-Solutions/bizzmind`: push в `main` = деплой на двата.
- Rewrite `/(.*)` → `/api/index.py?__path=$1`; `bizzmind/path_restore.py` възстановява пътя (Vercel не подава оригиналния).
- Data dir на Vercel е `/tmp/bizzmind` (кеш, пълни се от Supabase Storage).
- Web env се задава през REST API (CLI-ят се обърква от rootDirectory).

## Railway (алтернатива, ако Vercel лимитите станат проблем)
1. GitHub repo → New Project → Deploy from repo (Dockerfile се разпознава).
2. Втори service от същото repo: Settings → Start Command = `python worker.py`.
3. Variables: горните, и `PORT` се подава от Railway.

## Vercel (API само за enqueue/четене)
`vercel --prod` от корена; env променливите в Project Settings. Worker-ът остава на Railway.

## Локално
`./start.sh` — API (:8000) + worker (+ тунел). Тестове: `INLINE_JOBS=1` изпълнява AI задачите в заявката.
