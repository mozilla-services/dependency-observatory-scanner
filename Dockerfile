ARG BASE_IMAGE

FROM ${BASE_IMAGE}

RUN addgroup --gid 10001 app \
    && \
    adduser --gid 10001 --uid 10001 \
    --home /app --shell /sbin/nologin \
    --disabled-password app

RUN mkdir -p /app/bin/

USER app
WORKDIR /app

ADD ensure_repo.sh /app/bin/
ADD package_info.py /app/bin/

ENV PATH="/app/bin:${PATH}"
ENV GIT_REPO=
CMD /bin/bash /app/bin/ensure_repo.sh && /app/bin/package_info.py
