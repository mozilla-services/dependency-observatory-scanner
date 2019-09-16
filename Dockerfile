FROM python:3.7-slim-buster

# TODO: figure out perms to not run as root
# RUN addgroup --gid 10001 app \
#     && \
#     adduser --gid 10001 --uid 10001 \
#     --home /app --shell /sbin/nologin \
#     --disabled-password app
RUN mkdir -p /app
WORKDIR /app

COPY requirements.txt /app/
RUN pip install -r requirements.txt

COPY . .

ENV PYTHONPATH="fpr/:${PYTHONPATH}"
# USER app
CMD [ "python", "fpr/run_pipeline.py", "--help" ]
