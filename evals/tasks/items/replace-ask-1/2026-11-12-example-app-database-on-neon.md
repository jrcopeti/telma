---
date: 2026-11-12
status: active
source: own
---
# Example app database on Neon

**Decision (the owner, 2026-11-12):** the example app's database is Postgres on Neon, with a nightly
`pg_dump` to an S3 bucket kept for 30 days.

**Why:** Neon's free tier fits the app, and Neon's own restore only goes back 24 hours.
