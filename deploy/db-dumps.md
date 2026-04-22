# Production DB Dumps

Snapshots of the production `coalescence` database (Cloud SQL Postgres 16, instance `coalescence-db`, project `koalascience`) live in:

```
gs://koalascience-db-dumps/
```

## List existing dumps

```bash
gcloud storage ls --long gs://koalascience-db-dumps/
```

## Restore a dump locally

```bash
gcloud storage cp gs://koalascience-db-dumps/<filename>.sql.gz /tmp/dump.sql.gz
createdb coalescence_snapshot
zcat /tmp/dump.sql.gz | psql -v ON_ERROR_STOP=1 -d coalescence_snapshot
```

## Create a new dump

Filename convention: `coalescence-<reason>-<YYYY-MM-DD>.sql.gz`.

```bash
gcloud sql export sql coalescence-db \
  gs://koalascience-db-dumps/coalescence-<reason>-<YYYY-MM-DD>.sql.gz \
  --database=coalescence \
  --project=koalascience \
  --offload
```
