FROM python:3
RUN mkdir /config
COPY main.py /
COPY config.json /config/config.json
ENV MQTT_CLIENT_ID mijia
ENV MQTT_PUBLISH_DELAY 60
ENV MQTT_SERVER 127.0.0.1 
ENV MQTT_SERVER_PORT 1883
ENV MQTT_SERVER_KEEPALIVE 60
#ENV MQTT_USER mqttuser
#ENV MQTT_PASSWORD mqttpassword
ENV MQTT_BASE_TOPIC mijia
VOLUME /config
RUN pip install bluepy paho-mqtt
CMD [ "python", "main.py", "--config=/config/config.json" ]
