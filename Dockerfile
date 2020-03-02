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

RUN mkdir -p /app/fpr /app/bin

COPY --from=builder /tmp/build/venv /app/venv
COPY ./bin/analyze_package.sh /app/venv/bin
COPY ./bin/analyze_repo.sh /app/venv/bin

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
        apt-get upgrade -y && \
        apt-get install --no-install-recommends -y libpq-dev jq && \
        apt-get install --no-install-recommends -y \
            apt-transport-https \
            ca-certificates \
            curl \
            gnupg2 \
            software-properties-common \
            build-essential \
            libpq-dev && \
        curl -fsSL https://download.docker.com/linux/debian/gpg | apt-key add - && \
        add-apt-repository \
            "deb [arch=amd64] https://download.docker.com/linux/debian \
            $(lsb_release -cs) \
            stable" && \
        DEBIAN_FRONTEND=noninteractive apt-get update && \
        apt-get install --no-install-recommends -y \
            docker-ce \
            docker-ce-cli \
            containerd.io

WORKDIR /app
COPY fpr/ fpr/

CMD [ "python", "fpr/run_pipeline.py", "--help" ]
