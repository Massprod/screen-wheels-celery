import os
import json
import redis
import pyodbc
import requests
import requests.exceptions
from wheels_celery import app
from datetime import datetime, timezone
from wheels_actions import get_wheels_data, get_auth_token


REDIS_EXTRA_WHEELS_URL = os.getenv('REDIS_EXTRA_WHEELS_URL', 'redis://wheels_redis:6379/2')
FAILED_WHEELS_RECORD_NAME = os.getenv('FAILED_WHEELS_RECORD_NAME', 'failed_wheels_list')
CORRECT_WHEELS_RECORD_NAME = os.getenv('CORRECT_WHEELS_RECORD_NAME', 'correct_wheels_list')
PMK_PLATFORM_NAME = os.getenv('PMK_PLATFORM_NAME', 'pmkBase1')
STANDARD_PLACEMENT_STATUS = os.getenv('STANDARD_PLACEMENT_STATUS', 'basePlatform')
WHEELSTACK_MAX_SIZE = int(os.getenv('WHEELSTACK_MAX_SIZE', 6))


@app.task(name='sql_mark_read', bind=True, max_retries=3)
def sql_mark_read(
        self, 
        redis_url: str | None = None,
        record_name: str | None = None,
        driver: str = 'ODBC DRIVER 17 FOR SQL Server',
        server: str | None = None,
        database: str | None = None,
        username: str | None = None,
        password: str | None = None,
        table_name: str | None = None,
        use_timezone: bool = False,
):
    redis_url = os.getenv('REDIS_EXTRA_WHEELS_URL', redis_url)
    record_name = os.getenv('CORRECT_WHEELS_RECORD_NAME', record_name)
    if not any([redis_url, record_name]):
        raise Exception('Provide Redis data')
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
        'SQL_READ_TABLE', table_name
    )
    if not all([server, database, username, password, table_name]):
        raise Exception('Provide all SQL connection | table data')
    connection_string: str = (
        f'DRIVER={driver};'
        f'SERVER={server};'
        f'DATABASE={database};'
        f'UID={username};'
        f'PWD={password};'
    )
    sql_connection = None
    transferred_wheels = []
    try:
        redis_connection = redis.Redis.from_url(redis_url)
        wheel_records = redis_connection.lrange(record_name, 0, -1)
    except redis.exceptions.RedisError as error:
        self.retry(exc=error, countdown=15)
    for wheel_record in wheel_records:
        transferred_wheels.append(
            json.loads(wheel_record.decode('utf-8'))
        )
    if not transferred_wheels:
        return transferred_wheels
    try:
        sql_connection = pyodbc.connect(connection_string)
        cursor = sql_connection.cursor()
        # date_string = "CONVERT(DATETIMEOFFSET, ?, 127)" if use_timezone else "CONVERT(DATETIME, ?, 126)"
        # 127 == ISO 8601
        query = f"""
        UPDATE [{table_name}]
        SET mark = ?
        WHERE order_no = ? AND product_ID = ? AND marked_part_no = ? AND mark = 0;
        """
        # SQL - datetime <- can't store Timezone...
        # Using DATETIMEOFFSET <- getting it as string in `ISOformat` == ISO 8601
        # ^^^Not using this column.
        data = [
            (
                1, wheel_data['order_no'], wheel_data['product_ID'], wheel_data['marked_part_no']
            ) for wheel_data in transferred_wheels
        ]
        cursor.executemany(query, data)
        sql_connection.commit()
        for wheel_record in wheel_records:
            redis_connection.lrem(record_name, 0, wheel_record)
        return transferred_wheels
    except pyodbc.Error as error:
        self.retry(exc=error, countdown=15)
    except Exception as error:
        raise Exception(f'Error while updating SQL wheel records: {error}')
    finally:
        if sql_connection:
            sql_connection.close()


@app.task(name='redis_clear_failed_wheels', bind=True, max_retries=3)
def redis_clear_failed_wheels(
        self,
        redis_url: str | None = None,
        record_name: str | None = None,
        auth_address: str | None = None,
        auth_login: str | None = None,
        auth_password: str | None = None,
        api_address: str | None = None
):
    redis_url = os.getenv('REDIS_EXTRA_WHEELS_URL', redis_url)
    record_name = os.getenv('FAILED_WHEELS_RECORD_NAME', record_name)
    if not any([redis_url, record_name]):
        raise Exception('Provide Redis data')
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
    api_address: str = os.getenv(
        'API_ADDRESS', api_address
    )
    if not api_address:
        raise Exception('Provide `grid-api` address')
    # + AUTH TOKEN +
    auth_token: str = get_auth_token(auth_address, auth_login, auth_password)
    # - AUTH TOKEN -
    # + REDIS CLEARING +
    try:
        redis_connection = redis.Redis.from_url(redis_url)
        failed_wheels = redis_connection.lrange(record_name, 0, -1)
    except redis.exceptions.RedisError as error:
        self.retry(exc=error, countdown=15)
    cleared_wheels = []
    if not failed_wheels:
        return cleared_wheels
    delete_wheel_url: str = f'{api_address}/wheels'
    for wheel_record in failed_wheels:
        wheel_object_id: str = wheel_record.decode('utf-8')
        request_headers = {
            'Authorization': f'Bearer {auth_token}'
        }
        try:
            delete_resp = requests.delete(
                delete_wheel_url + f'/{wheel_object_id}',
                headers=request_headers,
                timeout=15,
            )
            if delete_resp.ok:
                cleared_wheels.append(wheel_object_id)
                redis_connection.lrem(record_name, 0, wheel_object_id)
        except (requests.exceptions.RequestException, Exception) as error:
            continue
    # - REDIS CLEARING -
    return cleared_wheels


@app.task(name='sql_transfer_wheels')
def sql_transfer_wheels(
        platform_name: str,
        auth_address: str = None,
        auth_login: str = None,
        auth_password: str = None,
        api_address: str = None,
        driver: str = 'ODBC DRIVER 17 FOR SQL Server',
        server: str | None = None,
        database: str | None = None,
        username: str | None = None,
        table_name: str | None = None,
        password: str | None = None,
        use_timezone: bool = False,
):
    # + REDIS CONNECTION +
    redis_connection = redis.Redis.from_url(REDIS_EXTRA_WHEELS_URL)
    # - REDIS CONNECTION -
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
        'SQL_READ_TABLE', table_name
    )
    if not all([server, database, username, password, table_name]):
        raise Exception('Provide all SQL connection | table data')
    connection_string: str = (
        f'DRIVER={driver};'
        f'SERVER={server};'
        f'DATABASE={database};'
        f'UID={username};'
        f'PWD={password};'
    )
    # + PLATFORM ID +
    platform_url: str = f'{api_address}/platform/name/{platform_name}'
    platform_headers: dict[str, str] = {
        'Authorization': f'Bearer {auth_token}'
    }
    platform_resp = requests.get(
        platform_url, headers=platform_headers
    )
    if not platform_resp.ok:
        raise Exception(f'Failed to get placement `objectId`. Status code: {platform_resp.status_code}, Response: {platform_resp.text}')
    platform_data = platform_resp.json()
    platform_id: str = platform_data['_id']    
    # - PLATFORM ID -
    wheels_data: list[dict] = get_wheels_data(connection_string, table_name)
    result: dict = {
        'createdWheels': [],
        'createdWheelstacks': [],
    }
    if not wheels_data:
        return result
    # Gather all data by corresponding `wheelstack`'s -> after getting wheels from MSQL.
    wheelstacks_data = {}
    for wheel_data in wheels_data:
        wheelstack_row: int = wheel_data['shuttle_number']
        if wheelstack_row not in wheelstacks_data:
            wheelstacks_data[wheelstack_row] = {}
        wheelstack_column: int = wheel_data['stack_number']
        if wheelstack_column not in wheelstacks_data[wheelstack_row]:
            wheelstacks_data[wheelstack_row][wheelstack_column] = {
                'originalWheels': [None for _ in range(10)],
                'createdWheels': [],
            }
        wheelstack_position: int = wheel_data['number_in_stack']
        wheelstacks_data[wheelstack_row][wheelstack_column]['originalWheels'][wheelstack_position] = wheel_data
    # Create wheels and place them in corresponding wheelstacks.
    create_wheel_url: str = f'{api_address}/wheels'
    failed_wheels: list[str] = []
    # [(row, col)]
    failed_wheelstacks: list[tuple[int, int]] = []
    for wheelstack_row in wheelstacks_data:
        for wheelstack_column in wheelstacks_data[wheelstack_row]:
            created_wheels: list[str] = wheelstacks_data[wheelstack_row][wheelstack_column]['createdWheels']
            original_wheels: list[dict] = wheelstacks_data[wheelstack_row][wheelstack_column]['originalWheels']
            for wheel_sql_data in original_wheels:
                if not wheel_sql_data:
                    continue
                wheel_id: str = str(wheel_sql_data['marked_part_no'])
                wheel_batch_number: str = str(wheel_sql_data['order_no'])
                receipt_date = None
                if use_timezone:
                    receipt_date = datetime.now(timezone.utc).isoformat()
                else:
                    receipt_date = datetime.now().isoformat()
                wheel_req_body: dict = {
                    'wheelId': wheel_id,
                    'batchNumber': wheel_batch_number,
                    'wheelDiameter': 10_000,
                    'receiptDate': receipt_date,
                    'status': 'basePlatform',
                    'sqlData': wheel_sql_data,
                }
                wheel_req_headers: dict[str, str] = {
                    'Content-type': 'application/json',
                    'Authorization': f'Bearer {auth_token}'
                }
                wheel_resp = requests.post(
                    create_wheel_url,
                    json=wheel_req_body,
                    headers=wheel_req_headers,
                    timeout=15,
                )
                if not wheel_resp.ok:
                    failed_wheels += created_wheels
                    failed_wheelstacks.append(
                        (wheelstack_row, wheelstack_column)
                    )
                    break
                created_wheel_data = wheel_resp.json()
                created_wheels.append(created_wheel_data['_id'])
    for row, col in failed_wheelstacks:
        del wheelstacks_data[row][col]
    create_wheelstack_url: str = f'{api_address}/wheelstacks'
    created_wheelstacks: list[str] = []
    for wheelstack_row in wheelstacks_data:
        for wheelstack_column in wheelstacks_data[wheelstack_row]:
            wheelstack_data = wheelstacks_data[wheelstack_row][wheelstack_column]
            wheelstack_wheels: list[str] = wheelstack_data['createdWheels']
            wheelstack_batch_number: str = ''
            for sql_wheel_data in wheelstack_data['originalWheels']:
                if not sql_wheel_data:
                    continue
                wheelstack_batch_number = str(sql_wheel_data['order_no'])
                break
            wheelstack_request_body: dict = {
                'placementId': platform_id,
                'placementType': STANDARD_PLACEMENT_STATUS,
                'rowPlacement': str(wheelstack_row),
                'colPlacement': str(wheelstack_column),
                'maxSize': WHEELSTACK_MAX_SIZE,
                'batchNumber': wheelstack_batch_number, 
                'blocked': False,
                'status': STANDARD_PLACEMENT_STATUS,
                'wheels': wheelstack_wheels,
            }
            wheelstack_request_headers: dict[str, str] = {
                'Content-type': 'application/json',
                'Authorization': f'Bearer {auth_token}',
            }
            wheelstack_resp = requests.post(
                create_wheelstack_url,
                json=wheelstack_request_body,
                headers=wheelstack_request_headers,
                timeout=15,
            )
            if 201 != wheelstack_resp.status_code:
                failed_wheels += wheelstack_wheels
                continue
            created_wheelstack_data = wheelstack_resp.json()
            for wheel_data in wheelstack_data['originalWheels']:
                if not wheel_data:
                    continue
                redis_connection.rpush(
                    CORRECT_WHEELS_RECORD_NAME,
                    json.dumps(wheel_data)
                )
            created_wheelstacks.append(created_wheelstack_data['_id'])
            sql_mark_read.delay()
    # Mark wheels for failed wheelstack | wheel creation, clearing them every 30s.
    # Because we don't care about empty wheels created in our MongoDB.
    # They will never affect anything, because we never use them by themselves.
    # It's either used with `wheelstack` or in `storage`.
    # But we only create new wheels in `basePlatform` <= we can clear them at anytime (just need to mark them).
    for wheel_object_id in failed_wheels:
        redis_connection.rpush(FAILED_WHEELS_RECORD_NAME, wheel_object_id)
    if failed_wheels:
        redis_clear_failed_wheels.delay()
    return {
        'createdWheelstacks': created_wheelstacks,
        'failedWheels': failed_wheels,
    }
