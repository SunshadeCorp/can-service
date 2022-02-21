FROM python:3-buster

WORKDIR /usr/src/app

RUN pip install Events~=0.4 paho-mqtt~=1.5.1 python-can~=3.3.3 PyYAML~=5.4.1

COPY . .

CMD [ "python", "./service.py" ]
