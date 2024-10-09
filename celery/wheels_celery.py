import os
from celery import Celery
from dotenv import load_dotenv


load_dotenv('.env')

PMK_PLATFORM_NAME = os.getenv('PMK_PLATFORM_NAME', 'pmkBase1')

broker_url = os.getenv('CELERY_BROKER_URL', 'redis://wheels_redis:6379/0')
backend_url = os.getenv('CELERY_RESULT_BACKEND', 'redis://wheels_redis:6379/1')

app = Celery(
    'wheels_transfer',
    broker=broker_url,
    backend=backend_url,
    broker_connection_retry_on_startup=True,
)

app.conf.timezone = 'UTC'

app.conf.task_queues = {
    'get_wheels_sql_que': {
        'exchange': 'get_wheels_sql_que',
        'routing_key': 'get_wheels_sql_que'
    },
    'extra_wheels_que': {
        'exchange': 'extra_wheels_que',
        'routing_key': 'extra_wheels_que',
    },
    'transfer_wheels_mongo_que': {
        'exchange': 'transfer_wheels_mongo_que',
        'routing_key': 'transfer_wheels_mongo_que'
    }
}

app.conf.beat_schedule = {
    'trigger_get_wheels_sql': {
        'task': 'sql_transfer_wheels',
        'schedule': 10.0,
        'args': (PMK_PLATFORM_NAME,),
    },
    'trigger_redis_clear_failed_wheels': {
        'task': 'redis_clear_failed_wheels',
        'schedule': 30.0,
        'args': (),
    },
    'trigger_redis_transfer_correct_wheels': {
        'task': 'sql_mark_read',
        'schedule': 30.0,
        'args': (),
    },
    'trigger_transfer_wheels_mongo': {
        'task': 'transfer_wheels_mongo',
        'schedule': 30.0,
        'args': (),
    }
}

app.conf.task_default_queue = 'get_wheels_sql_que'

app.conf.task_routes = {
    'sql_transfer_wheels' : {
        'queue': 'get_wheels_sql_que',
    },
    'sql_mark_read': {
        'queue': 'extra_wheels_que',
    },
    'redis_clear_failed_wheels': {
        'queue': 'extra_wheels_que',
    },
    'transfer_wheels_mongo': {
        'queue': 'transfer_wheels_mongo_que',
    },
}

app.autodiscover_tasks(['sql_mongo_transfer', 'mongo_sql_transfer'], force=True)
