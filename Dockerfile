FROM python:3.12-slim

WORKDIR /app

ADD ./requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

ADD ./backlog_keeper /app/backlog_keeper

ENV PYTHONPATH=/app

CMD ["python", "-m", "backlog_keeper.main"]