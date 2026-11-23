# PostgreSQL test-tier baseline (ENG-17)

The reports PostgreSQL tier (`tests/reports/pg/`) builds its schema the way every client database is built
(`docs/onboarding/NEW_CLIENT_DATABASE.md` §1.3-1.4): restore a structure-only dump, stamp its Alembic revision,
`alembic upgrade head`. It needs two committed files here:

| File | Content |
|---|---|
| `baseline_schema.sql` | `pg_dump --schema-only --no-owner --no-privileges` of the migrated source database (structure only, no data) |
| `baseline_revision.txt` | the `version_num` of that database's `alembic_version` table at dump time (one line) |

Produce them (a person runs this; it only reads the schema):

```bash
pg_dump -h DB_IP -U dentc_dev_user --schema-only --no-owner --no-privileges -f tests/pg/baseline_schema.sql recondental_migrated
psql -h DB_IP -U dentc_dev_user -d recondental_migrated -t -A -c "select version_num from alembic_version" > tests/pg/baseline_revision.txt
```

Check the dump contains no data (`grep -c "^COPY " tests/pg/baseline_schema.sql` prints 0) before committing.
Refresh both files when the main client's schema moves far ahead (the nightly migration smoke will do this later).

Running the tier: set `TEST_DATABASE_URL` to a PostgreSQL 15 server and a database the role may connect to
(CREATEDB privilege required), then `pytest tests/reports`. The tier creates, migrates and drops only databases
named `rpt_test_*` and runs nothing else on that server. Locally: `docker compose up -d postgres` and
`TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/postgres`.
