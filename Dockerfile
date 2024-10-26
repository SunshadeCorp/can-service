FROM python:3.12-alpine

WORKDIR /usr/src/app

COPY . .

RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

CMD [ "python", "./service.py" ]
