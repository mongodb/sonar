FROM python:3.9-slim

COPY . /src

RUN pip install -r /src/requirements.txt

WORKDIR /src/
ENTRYPOINT pytest
