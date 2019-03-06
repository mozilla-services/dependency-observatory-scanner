ARG BASE_IMAGE

FROM ${BASE_IMAGE}

RUN addgroup --gid 10001 app \
    && \
    adduser --gid 10001 --uid 10001 \
    --home /app --shell /sbin/nologin \
    --disabled-password app

RUN mkdir -p /tmp/bin/

ENV PATH="/tmp/bin:${PATH}"

USER app
WORKDIR /app
