FROM python:3.7

RUN echo “Asia/Shanghai” > /etc/timezone

WORKDIR /app

COPY requirements.txt /app/

RUN pip install -r requirements.txt

COPY . /app


CMD celery -A tasks worker --loglevel=debug -c 2 -P eventlet && celery beat -A tasks
