FROM python:3.12-alpine

WORKDIR /usr/src/app

COPY . .

RUN apk --no-cache add --virtual build-deps build-base && \
    pip install --no-cache-dir --prefer-binary -r requirements.txt && \
    apk del build-deps

CMD [ "python", "./service.py" ]
