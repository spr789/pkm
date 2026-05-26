# ============================================================
#  PKM — Quick shortcuts / copy-paste reference
# ============================================================

# ----- venv -------------------------------------------------
. .venv/Scripts/activate          # activate virtual env (Git Bash)
.venv\Scripts\activate            # activate (cmd / pwsh)

# ----- run app (Telegram bot) -------------------------------
python -m app.main                # start bot polling

# ----- database (Alembic) -----------------------------------
alembic revision --autogenerate -m "describe_change"
alembic upgrade head
alembic downgrade -1

# ----- quality ----------------------------------------------
ruff check .                      # lint
ruff format .                     # format
ruff check --fix .                # lint + auto-fix

# ----- test -------------------------------------------------
pytest                            # run all tests
pytest -v -k "test_name"          # run specific test

# ----- git --------------------------------------------------
git add -A && git commit -m "message" && git push
git add -A && git commit -m "message"
git log --oneline -10
git pull --rebase
git reset HEAD~1                  # undo last commit (keep changes)
git reset --hard HEAD~1           # undo last commit (discard changes)

# ----- deps ------------------------------------------------
pip install -e ".[dev,ai]"        # install project + dev + ai deps
pip freeze > requirements.txt     # snapshot current deps
