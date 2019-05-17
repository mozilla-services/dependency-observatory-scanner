FROM python:3-slim

RUN addgroup --gid 10001 app \
    && \
    adduser --gid 10001 --uid 10001 \
    --home /app --shell /sbin/nologin \
    --disabled-password app

ADD README.md /app
ADD requirements.txt /app
ADD setup.py /app
COPY github_metadata_fetcher/ /app/github_metadata_fetcher/

WORKDIR /app
RUN pip install -e .

USER app
CMD ["python", "fetch_github_metadata"]
