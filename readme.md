!
<br> Все ссылания на переменные идут для `.env`
<br>В котором находятся все основные переменные для корректировки.
<br>Создайте или используйте базовый с редакцией **логин/пароль**.
<br>!
------------------------------
Необходимые предустановки
------------------------------
- [Docker](https://www.docker.com/)
- [WSL2](https://learn.microsoft.com/ru-ru/windows/wsl/install) <- используется самим Docker (если используете без него, должно работать и так)<br>Используется для создания ключа, поэтому если ключ будет создаваться по пункту `1` необходимо к использованию<br>(либо используйте другой способ создания ключа)
------------------------------
Последовательность запуска:
------------------------------
Все приведённые команды с учётом запуска из рабочей директории `docker-compose.yml`.
1. **Запуск Docker:**
    Из рабочей директории приложения с `docker-compose.yml` 
   ```commandline
   docker-compose up --no-start --build -d
   ``` 
   1. Запустите контейнер [Redis](https://redis.io/):
   ```commandline
   docker start wheels_redis
   ```
   2. Запустите контейнер работников [celery](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html): 
   ```commandline
   docker start wheels-celery-workers
   ```
   3. Запустите контейнер мониторинга [flower](https://flower.readthedocs.io/en/latest/): 
   ```commandline
   docker start wheels_flower
   ```
2. **Проверьте рабочий статус c помощью `flower` перейдя `localhost:5555`**
   <br>(Измените домейн + порт в соответствии с вашими данными)
------------------------------
Описание переменных `.env` для `compose`:
------------------------------
- `REDIS_CONTAINER_NAME` <- наименование контейнера для базы данных [Redis](https://redis.io/)
- `REDIS_OUTSIDE_PORT` <- открываемый внешний порт контейнера [Redis](https://redis.io/)
- `REDIS_INSIDE_PORT` <- открываемый внутренний порт контейнера [Redis](https://redis.io/)
- `CELERY_BROKER_URL` <- адрес [Redis](https://redis.io/) для использования [celery](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
- `WHEELS_CELERY_WORKERS_CONTAINER_NAME` <- наименование контейнера для работников [celery](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
- `WHEELS_FLOWER_CONTAINER_NAME` <- наименование контейнера для мониторинга [flower](https://flower.readthedocs.io/en/latest/)
- `WHEELS_FLOWER_OUTSIDE_PORT` <- открываемый внешний порт контейнера [flower](https://flower.readthedocs.io/en/latest/)
- `WHEELS_FLOWER_INSIDE_PORT` <- открываемый внутренний порт контейнера [flower](https://flower.readthedocs.io/en/latest/)
- `FLOWER_LOGIN` <- логин используемый для авторизации в сервисе мониторинга [flower](https://flower.readthedocs.io/en/latest/)
- `FLOWER_PASSWORD` <- пароль используемый для авторизации в сервисе мониторинга [flower](https://flower.readthedocs.io/en/latest/)
------------------------------
Описание переменных `.env` для [celery](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html):
------------------------------
- `AUTH_ADDRESS` <- адрес сервиса аутентификации, используемого для получения [JWT](https://jwt.io/) и авторизации запросов к основному сервису
- `AUTH_LOGIN` <- логин используемый для получения [JWT](https://jwt.io/) от сервиса авторизации
- `AUTH_PASSWORD` <- пароль используемый для получения [JWT](https://jwt.io/) от сервиса авторизации
- `API_ADDRESS` <- адрес основного сервиса
- `SQL_ADDRESS` <- адрес MSQL сервера
- `SQL_DATABASE` <- наименование базы данных для использования
- `SQL_NAME` <- логин для авторизации подключения к MSQL
- `SQL_PASSWORD` <- пароль для авторизации подключения к MSQL
- `SQL_READ_TABLE` <- название стола(таблицы) для получения данных
- `SQL_WRITE_TABLE` <- название стола(таблицы) для записи данных
- `CELERY_BROKER_URL` <- адрес [Redis](https://redis.io/) для использования брокером [celery](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html). Должен совпадать с указанным в `compose`
- `CELERY_RESULT_BACKEND` <- адрес [Redis](https://redis.io/) для использования бэкендом [celery](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
- `REDIS_EXTRA_WHEELS_URL` <- адрес [Redis](https://redis.io/) для использования как дополнительное хранилище переносов для сервиса [celery](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
- `FAILED_WHEELS_RECORD_NAME` <- наименование(ключ) используемый для идентификации неудачных попыток переноса из `REDIS_EXTRA_WHEELS_URL`
- `CORRECT_WHEELS_RECORD_NAME` <- наименование(ключ) используемый для идентификации успешных переносов из `REDIS_EXTRA_WHEELS_URL` 
- `PMK_PLATFORN_NAME` <- стандартное наименование челнока, используемого для заполнения
- `WHEELSTACK_MAX_SIZE` <- максимальный размер собираемых стоп
- `STANDARD_PLACEMENT_STATUS` <- стандартное наименование статуса для помещаемых в приямок стоп