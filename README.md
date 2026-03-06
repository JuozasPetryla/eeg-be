# Psich.ai

## Setup

Go to readme of -> https://github.com/JuozasPetryla/eeg-infra

Additionally set a `venv` locally:

```
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Usage

After successful setup, API should reachable on `http://localhost:8000`

As well as documentation on `http://localhost:8000/docs`

## Migrations

To perform database migrations, you first need to modify or add models in the `app/core/models/` directory

After addding or modifying a model run:

- `docker compose run --rm eeg-be alembic revision --autogenerate -m "Migration message"`

This will auto generate an alembic revision file and to apply the changes to the actual database run:

- `docker compose run --rm eeg-be alembic upgrade head`
