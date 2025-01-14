import pyodbc
import requests
from datetime import datetime, timezone, timedelta


def get_auth_token(auth_address: str, auth_login: str, auth_password: str) -> str:
    auth_url = f'{auth_address}/users/login'
    auth_body = {
        'username': auth_login,
        'password': auth_password,
    }
    auth_headers = {
        'Content-type': 'application/x-www-form-urlencoded',
    }
    try:
        token_resp = requests.post(auth_url, data=auth_body, headers=auth_headers, timeout=15)
        token_resp.raise_for_status()  # Automatically raise HTTPError if status is 4xx/5xx
        auth_resp_data = token_resp.json()
        return auth_resp_data['access_token']
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to authenticate: {e}")


def get_wheels_data(
        connection: pyodbc.Connection,
        table_name: str,
        shuttle_number: int = 0,
        close_connection: bool = False,
) -> list[dict]:
    try:
        # + SHUTTLE READY +
        ready_column = 'wheels_unloading'
        cursor = connection.cursor()
        # - SHUTTLE READY -
        cursor = connection.cursor()
        cursor.execute((
            f'SELECT ' 
            f'  [{table_name}].order_no, '
            f'  [{table_name}].year, '
            f'  [{table_name}].product_ID, '
            f'  [{table_name}].marked_part_no, '
            f'  [{table_name}].shuttle_number, '
            f'  [{table_name}].stack_number, '
            f'  [{table_name}].number_in_stack, '
            f'  [{table_name}].timestamp_submit, '
            f'  [{table_name}].mark '
            f'FROM [{table_name}] '
            f'WHERE [{table_name}].mark = 0 '
            f'AND '
            f'[{table_name}].{ready_column} = ('
            f'  SELECT MIN([{table_name}].{ready_column}) '
            f'  FROM [{table_name}] '
            f'  WHERE '
            f'  [{table_name}].mark = 0 '
            f'  AND '
            f'  [{table_name}].shuttle_number = ? '
            f'  AND '
            f'  [{table_name}].marked_part_no <> 1111 '
            f') '
            f'AND '
            f'[{table_name}].marked_part_no <> 1111 '
            f'ORDER BY [{table_name}].timestamp_submit;'
        ), shuttle_number)
        wheel_records = cursor.fetchall()
        wheels_data: list[dict] = []
        table_columns: list[str] = [column[0] for column in cursor.description]
        for wheel_record in wheel_records:
            wheel_data = dict(zip(table_columns, wheel_record))
            wheel_data['timestamp_submit'] = datetime.now().isoformat()
            wheels_data.append(wheel_data)
        return wheels_data
    except Exception as error:
        raise Exception(f'Error while getting wheels data: {error}')
    finally:
        if close_connection and connection:
            connection.close()


def sql_check_transfer_record(
        sql_connection,
        table_name: str,
        wheel_data: dict,
):
    cursor = None
    try:
        cursor = sql_connection.cursor()
        query = f"""
        SELECT 
            [{table_name}].order_no
        FROM [{table_name}]
        WHERE
            [{table_name}].order_no = ? AND 
            [{table_name}].year = ? AND 
            [{table_name}].product_ID = ? AND 
            [{table_name}].marked_part_no = ?;
        """
        data = (
            wheel_data['sqlData']['order_no'],
            wheel_data['sqlData']['year'],
            wheel_data['sqlData']['product_ID'],
            wheel_data['sqlData']['marked_part_no']
        )
        cursor.execute(
            query, data
        )
        result = cursor.fetchall()
        return result
    except Exception as error:
        raise Exception(f'Error while getting wheels data: {error}')
    finally:
        if cursor:
            cursor.close()


def sql_create_transfer_record(
        sql_connection: pyodbc.Connection,
        table_name: str,
        wheel_data: dict,
        timestamp: datetime,
):
    cursor = None
    try:
        cursor = sql_connection.cursor()
        wheel_status = wheel_data['status']
        # order_status == batch_status
        batch_translate = {
            'laboratory': 0,
            'shipped': 1,
            'pto': 2,  # not used, but w.e
            'rejected': 3,
        }
        # product_state == wheel status (as 1 unit)
        wheel_status_translate = {
            'shipped': 0,
            'laboratory': 1,
            'rejected': 2,
        }
        # We're always removing `wheel` from wheelstack when it's going to the lab.
        # So, marking it as `-1` == non existing.
        wheelstack_position = -1
        wheelstack = wheel_data['wheelStack']
        if wheelstack:
            wheelstack_position = wheelstack['wheelStackPosition']
        query = f"""
        INSERT INTO [{table_name}] (
            order_no,
            year,
            product_ID,
            marked_part_no,
            number_virtual_position,
            number_in_stack,
            timestamp_submit,
            order_status,
            product_state,
            RW_Recipe_ID,
            mark
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        data = (
            wheel_data['sqlData']['order_no'],
            wheel_data['sqlData']['year'],
            wheel_data['sqlData']['product_ID'],
            wheel_data['sqlData']['marked_part_no'],
            wheel_data['sqlData'].get('virtualPosition', 0),
            wheelstack_position,
            timestamp,
            batch_translate[wheel_status],
            wheel_status_translate[wheel_status],
            0,  # not used yet.
            0,  # 0 == we only add, other service reads and marks with `1`` later 
        )
        result = cursor.execute(query, data)
        sql_connection.commit()
        return result.rowcount
    except Exception as error:
        raise Exception(f'Error while creating wheel record: {error}')
    finally:
        if cursor:
            cursor.close()
