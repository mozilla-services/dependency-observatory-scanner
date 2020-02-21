FROM python:3.8-slim-buster

RUN addgroup --gid 10001 app \
    && \
    adduser --gid 10001 --uid 10001 \
    --home /app --shell /sbin/nologin \
    --disabled-password app
USER app

RUN mkdir -p /app
WORKDIR /app

COPY requirements.txt.lock /app/
RUN pip install -r requirements.txt.lock

COPY . .

ENV PYTHONPATH="fpr/:${PYTHONPATH}"
CMD [ "python", "fpr/run_pipeline.py", "--help" ]
