FROM python:3-buster

WORKDIR /usr/src/app

RUN pip install Events~=0.4 paho-mqtt~=2.1.0 python-can~=3.3.3 PyYAML~=6.0.1

COPY . .

CMD [ "python", "./service.py" ]
