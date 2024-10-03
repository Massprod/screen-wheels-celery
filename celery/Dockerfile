FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unixodbc \
    unixodbc-dev \
    apt-transport-https \
    gcc \
    g++

# Install Microsoft ODBC Driver for SQL Server (Ubuntu/Debian-based systems)
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17

RUN useradd --create-home --shell /bin/bash celeryuser

WORKDIR /app

COPY . .

RUN chown -R celeryuser:celeryuser /app

RUN pip install --upgrade pip && pip install -r requirements.txt

USER celeryuser

# `concurrency=1` <- because we don't want to have duplicates, and there's no reasons to call DB for checks on every record.
# Extra, we're not guaranted that data is going to be unique, so it's better to escape ANY dangers and just use `1` worker.
# It's only 8 records at a time, and MONGO -> SQL transfer is made with `extra_actions` == concurrent AF.
CMD ["sh", "-c", "celery -A wheels_celery worker -n sql_mongo_gather -Q get_wheels_sql_que --concurrency=1 --loglevel=info & \
    celery -A wheels_celery worker -n mongo_sql_gather -Q transfer_wheels_mongo_que --concurrency=1 --loglevel=info & \
    celery -A wheels_celery worker -n extra_actions -Q extra_wheels_que --loglevel=info & \
    celery -A wheels_celery beat --loglevel=info"]
