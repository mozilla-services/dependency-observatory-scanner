FROM python:3.7-slim

RUN addgroup --gid 10001 app \
    && \
    adduser --gid 10001 --uid 10001 \
    --home /app --shell /sbin/nologin \
    --disabled-password app

ADD requirements-lock.txt /app

RUN pip install --no-cache-dir -r /app/requirements-lock.txt

ADD fetch_github_metadata_for_repo.py /app

USER app
WORKDIR /app
CMD ["python", "/app/fetch_github_metadata_for_repo.py"]
