# Postgres 16 with pgvector (apt) + Apache AGE (bundled in base image).
# Mirrors astrocyte's own docker/postgres-age-pgvector/Dockerfile.
FROM apache/age:release_PG16_1.6.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
