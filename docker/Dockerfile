FROM python:3.7-slim

COPY . /src

RUN pip install -r /src/requirements.txt

WORKDIR /src/
ENTRYPOINT pytest
