# StudyPLUS

A small local learning app with separate School AI search, Programming Class quizzes, and language sessions. It uses only Python's standard library and SQLite.

## Run locally

1. Install Python 3.10 or newer.
2. Copy `.env.example` to `.env` and set `STUDYPLUS_OWNER_EMAIL` to the owner email.
3. Start the app with `python server.py`.
4. Open [http://localhost:8000](http://localhost:8000).
5. On first launch, create the owner password. New members can register with email and password; no verification code is used.

The app creates `studyplus.db` in this folder. It stores accounts, classes, quizzes, and quiz scores. Passwords are salted and hashed. The database and `.env` are excluded from Git by `.gitignore`.

## GitHub hosting

GitHub stores this source code, but GitHub Pages cannot run the Python API or SQLite database. Opening the repository or enabling Pages alone will not run the app. Run it locally with the steps above, or deploy `server.py` to a Python host with persistent disk storage for SQLite.

## Features

- **School AI:** opens a Google search for a study question. In-app AI-written answers are not connected yet; that needs an AI provider configuration.
- **Programming Class:** teachers, admins, and the owner can create quizzes. Members can take them and get a score.
- **Language sessions:** members can join sessions. Teachers can schedule sessions and add secure meeting links.
- **Member roles:** owner and admins can assign student, teacher, helper, or admin roles.
- **Reports and bans:** staff can submit ban requests; only the owner can approve requests or ban/unban a member.
- **Maintenance mode:** the owner can pause access for everyone else.

## GitHub notes

This repository contains application source only. Never commit `.env`, `studyplus.db`, passwords, or API keys. The local SQLite database may contain private account information and quiz history.

This is a local prototype. Before exposing it to the public internet, add HTTPS, production-grade session and request protections, backups, and the chosen AI provider integration. No license has been selected yet.
