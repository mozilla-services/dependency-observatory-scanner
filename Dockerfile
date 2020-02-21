FROM python:3.8-slim-buster as builder
ENV PYTHONUNBUFFERED 1
ENV DEV 0

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
	apt-get upgrade -y && \
	apt-get install --no-install-recommends -y build-essential libpq-dev

RUN mkdir -p /tmp/build
WORKDIR /tmp/build

COPY ./bin/install.sh .
COPY requirements.txt.lock .
COPY dev-requirements.txt.lock .

RUN ./install.sh

FROM python:3.8-slim-buster as runtime
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH="/app/fpr/:${PYTHONPATH}"
ENV PATH="/app/venv/bin:$PATH"

RUN mkdir -p /app/fpr

COPY --from=builder /tmp/build/venv /app/venv

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
	apt-get upgrade -y && \
	apt-get install --no-install-recommends -y libpq-dev

WORKDIR /app
COPY fpr/ fpr/

CMD [ "python", "fpr/run_pipeline.py", "--help" ]
