import os
import pyodbc
import requests
from wheels_celery import app
from datetime import datetime, timezone
from wheels_actions import get_auth_token, sql_check_transfer_record, sql_create_transfer_record


@app.task(name='transfer_wheels_mongo')
def transfer_wheels_mongo(
        driver: str = 'ODBC DRIVER 17 FOR SQL Server',
        server: str | None = None,
        database: str | None = None,
        username: str | None = None,
        password: str | None = None,
        table_name: str | None = None,
        auth_address: str | None = None,
        auth_login: str | None = None,
        auth_password: str | None = None,
        api_address: str | None = None,
        use_timezone: bool = False,
):
    auth_address: str = os.getenv(
        'AUTH_ADDRESS', auth_address
    )
    auth_login: str = os.getenv(
        'AUTH_LOGIN', auth_login
    )
    auth_password: str = os.getenv(
        'AUTH_PASSWORD', auth_password
    )
    if not all([auth_address, auth_login, auth_password]):
        raise Exception('Provide authentication data')
     # + AUTH TOKEN +
    auth_token: str = get_auth_token(auth_address, auth_login, auth_password)
    # - AUTH TOKEN -
    api_address: str = os.getenv(
        'API_ADDRESS', api_address
    )
    if not api_address:
        raise Exception('Provide `grid-api` address')
    server: str = os.getenv(
        'SQL_ADDRESS', server
    )
    database: str = os.getenv(
        'SQL_DATABASE', database
    )
    username: str = os.getenv(
        'SQL_NAME', username
    )
    password: str = os.getenv(
        'SQL_PASSWORD', password
    )
    table_name: str = os.getenv(
        'SQL_WRITE_TABLE', table_name
    )
    if not all([server, database, username, password, table_name]):
        raise Exception('Provide all SQL connection | table data')
    # + SQL connection +
    connection_string: str = (
        f'DRIVER={driver};'
        f'SERVER={server};'
        f'DATABASE={database};'
        f'UID={username};'
        f'PWD={password};'
    )
    sql_connection = pyodbc.connect(connection_string)
    # - SQL connection -
    # + GET WHEELS TO TRANSFER +
    transfer_wheels_url = f"{api_address}/wheels/transfer/all?include_data=true&transfer_status=false&correct_status=true"
    auth_req_headers = {
        'Authorization': f'Bearer {auth_token}'
    }
    transfer_wheels_resp = requests.get(transfer_wheels_url, headers=auth_req_headers)
    if not transfer_wheels_resp.ok:
        raise Exception(f'Failed to get data: {transfer_wheels_resp.status} | {transfer_wheels_resp.text}')
    transfer_wheels_data = transfer_wheels_resp.json()
    # - GET WHEELS TO TRANSFER -
    transferred_wheels = []
    failed_wheels = []
    # Should be failprove, so we don't care about added or not records.
    # We either can commit and create record and we will update it in Mongo.
    # Or we fail whole task with SQL_connection error.
    # If we fail Mongo update, we don't care => we will just check that SQL record exists and mark it anyway.
    # SQL will never get duplicates, because we always check
    # And Mongo will be marked, only if we have record or created a record, so it should be 99% correct.
    for wheel_data in transfer_wheels_data:
        exists = sql_check_transfer_record(
            sql_connection, table_name, wheel_data
        )
        timestamp = None
        if use_timezone:
        # Format as 'YYYY-MM-DD HH:MM:SS'
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        else:
            timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        if not exists:
            sql_create_transfer_record(
                sql_connection, table_name, wheel_data, timestamp
            )
        upd_wheel_transfer_status_url = f'{api_address}/wheels/transfer/update/{wheel_data['_id']}?transfer_status=true'
        upd_resp = requests.patch(upd_wheel_transfer_status_url, headers=auth_req_headers)
        if upd_resp.ok:
            transferred_wheels.append(wheel_data['_id'])
            continue
        failed_wheels.append(wheel_data['_id'])
    sql_connection.close()
    return {
        'transferred_wheels': transferred_wheels,
        'failed_wheels': failed_wheels,
    }
