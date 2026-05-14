"""Settings di CI: estende quelle di sviluppo ma forza SQLite in-memory.

Usato dal workflow `.github/workflows/ci.yml` per eseguire `manage.py check`
e `manage.py makemigrations --check --dry-run` senza dover stare in piedi un
Postgres durante la CI: i due comandi sono check di metadata e non hanno
bisogno della vera struttura del DB di produzione.
"""
from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
