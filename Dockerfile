FROM alpine:3.4

ENV PYTHONUNBUFFERED 1

RUN apk update && \
    apk add \
        python3 \
        python3-dev \
        freetds \
        unixodbc-dev \
        memcached-dev \
        libmemcached-dev \
        cyrus-sasl-dev \
        zlib-dev \
        g++

COPY odbcinst.ini /etc

RUN mkdir /app
COPY . /app
WORKDIR /app

RUN pip3 install -r /app/requirements.txt

CMD ["python3", "src/focus.py"]
