#!/usr/bin/env python3

"""MiJia GATT to MQTT"""

import re
import time
import argparse
import json
import os
import argparse

import paho.mqtt.client as mqtt
from bluepy import btle

MQTT_CLIENT_ID = ''
MQTT_PUBLISH_DELAY = 0
MQTT_SERVER = ''
MQTT_SERVER_PORT = 0
MQTT_SERVER_KEEPALIVE = 0
MQTT_USER = ''
MQTT_PASSWORD = ''
MQTT_BASE_TOPIC = ''
HCI_DEV_NO = 0

MIJIA_BATTERY_SERVICE_UUID = btle.UUID('180f')
MIJIA_BATTERY_CHARACTERISTIC_UUID = btle.UUID('2a19')

MIJIA_DATA_SERVICE_UUID = btle.UUID('226c0000-6476-4566-7562-66734470666d')
MIJIA_DATA_CHARACTERISTIC_UUID = btle.UUID('226caa55-6476-4566-7562-66734470666d')
MIJIA_DATA_CHARACTERISTIC_HANDLE = 0x0010

BTLE_SUBSCRIBE_VALUE = bytes([0x01, 0x00])
BTLE_UNSUBSCRIBE_VALUE = bytes([0x00, 0x00])

j = None
d = {}


class MyDelegate(btle.DefaultDelegate):
    mijia = ""

    def __init__(self, dev):
        self.mijia = dev
        btle.DefaultDelegate.__init__(self)

    def handleNotification(self, cHandle, data):
        global d

        pattern = re.compile('T=([\d.-]+) H=([\d.-]+)')
        match = re.match(pattern, bytearray(data).decode('utf-8'))
        if match:
            d[self.mijia][0] = match.group(1)
            d[self.mijia][1] = match.group(2)


class MyCommClass():

    def __init__(self):
        print('Comm class initializing.')

    def do_comm(self):
        global j, d, mqtt_client_connected

        for x in range(0,len(j)):
            d[j[x]['Name']] = [0, 0, 0, 'init', 'not used']

        mqttc = mqtt.Client(MQTT_CLIENT_ID)
        if MQTT_PASSWORD is not None and MQTT_USER is not None:
            mqttc.username_pw_set(MQTT_USER, MQTT_PASSWORD)

        mqtt_topic_state = MQTT_BASE_TOPIC 
        mqttc.will_set(mqtt_topic_state, '{"status" : "disconnected"}', 1, True)
        mqttc.user_data_set(mqtt_topic_state)
        mqttc.connected_flag = False
        mqttc.bad_connection_flag = False

        mqttc.on_connect = self.on_connect
        mqttc.on_disconnect = self.on_disconnect

        try:
            print('Trying to connect to: ' + MQTT_SERVER + ' on port: ' + str(MQTT_SERVER_PORT) + ' with keep alive: ' + str(MQTT_SERVER_KEEPALIVE))
            mqttc.connect(MQTT_SERVER, MQTT_SERVER_PORT, MQTT_SERVER_KEEPALIVE)
            mqttc.loop_start()

            print('Connecting to MQTT broket: ' + MQTT_SERVER + ' on port: ' + str(MQTT_SERVER_PORT))
            while not mqttc.connected_flag and not mqttc.bad_connection_flag:  # wait in loop
                time.sleep(1)
            if mqttc.bad_connection_flag:
                mqttc.loop_stop()
                return

            last_msg_time = time.time()

            while True:

                for x in range(0, len(j)):

                    try:
                        mijia_blte_address = j[x]['mac']
                        print('Connecting to: ' + j[x]['Name'] + " with mac: " + j[x]['mac'])
                        dev = btle.Peripheral(mijia_blte_address,btle.ADDR_TYPE_PUBLIC,HCI_DEV_NO)
                        #mqttc.publish(MQTT_BASE_TOPIC + '/' + j[x]['Name'] + '/status', 'connected', 1, True)
                        d[j[x]['Name']][4] = 'connected'
                    except btle.BTLEDisconnectError:
                        print("Could not connect to: " + j[x]['Name'] + " with mac: " + j[x]['mac'])
                        mqttc.publish(MQTT_BASE_TOPIC + '/' + j[x]['Name'], '{"status" : "comm error"}', 1, True)
                        d[j[x]['Name']][4] = 'comm error'
                        #self.publish_sensor_data(mqtcc, MQTT_BASE_TOPIC + '/' + j[x]['Name'], d[j[x]['Name']])
                        continue

                    dev.setDelegate(MyDelegate(j[x]['Name']))

                    try:
                        # Get battery level
                        d[j[x]['Name']][3] = self.fetch_battery_level(dev)
                        print('Battery level: ' + str(d[j[x]['Name']][3]))

                        # Subscribe to data characteristic
                        dev.writeCharacteristic(MIJIA_DATA_CHARACTERISTIC_HANDLE, BTLE_SUBSCRIBE_VALUE, True)
                        # while True:
                        if dev.waitForNotifications(5.0):
                            print('Temperature: ' + d[j[x]['Name']][0])
                            print('Humidity: ' + d[j[x]['Name']][1])
                            dev.writeCharacteristic(MIJIA_DATA_CHARACTERISTIC_HANDLE, BTLE_UNSUBSCRIBE_VALUE, True)
                            #self.publish_sensor_data(mqttc, MQTT_BASE_TOPIC + '/' + j[x]['Name'], d[j[x]['Name']])

                        self.publish_sensor_data(mqttc, MQTT_BASE_TOPIC + '/' + j[x]['Name'], d[j[x]['Name']])

                        dev.disconnect()
                        #mqttc.publish(MQTT_BASE_TOPIC + '/' + j[x]['Name'] + '/status', 'disconnected', 1, True)

                    except btle.BTLEDisconnectError:
                        print("Failed to get data from " + j[x]['Name'] + " with mac: " + j[x]['mac'])
                        mqttc.publish(MQTT_BASE_TOPIC + '/' + j[x]['Name'], '{"status" : "data failure"}', 1, True)

                delay_gap = time.time() - last_msg_time
                if delay_gap < MQTT_PUBLISH_DELAY:
                    time.sleep(MQTT_PUBLISH_DELAY - delay_gap)
                    last_msg_time = time.time()
        except IOError:
            print('MQTT Connection Broken!')

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print('Connected to MQTT broker')
            client.publish(userdata, 'connected', 1, True)
            client.connected_flag = True
        else:
            print('Failed to connect to MQTT broker with rc: ' + str(rc))
            client.bad_connection_flag = True

    def on_disconnect(self, client, userdata, rc):
        print('Disconnected from MQTT broker with rc: ' + str(rc))
        client.connected_flag = False
        client.disconnect_flag = True

    def fetch_battery_level(self, dev):
        battery_service = dev.getServiceByUUID(MIJIA_BATTERY_SERVICE_UUID)
        battery_characteristic = battery_service.getCharacteristics(MIJIA_BATTERY_CHARACTERISTIC_UUID)[0]
        return ord(battery_characteristic.read())

    def publish_sensor_data(self, mqttc, topic, mijia):
        json_payload = {}
        json_payload['temperature'] = mijia[0]
        json_payload['humidity'] = mijia[1]
        json_payload['battery'] = mijia[3]
        json_payload['status'] = mijia[4]
        print('MQTT Topic: ' + topic)
        print('JSON payload: ' + json.dumps(json_payload))
        mqttc.publish(topic, json.dumps(json_payload),1,True)

def main():
    global MQTT_CLIENT_ID
    global MQTT_PUBLISH_DELAY
    global MQTT_SERVER
    global MQTT_SERVER_PORT
    global MQTT_SERVER_KEEPALIVE
    global MQTT_USER
    global MQTT_PASSWORD
    global MQTT_BASE_TOPIC
    global HCI_DEV_NO
    global j

    MQTT_CLIENT_ID = os.getenv('MQTT_CLIENT_ID', 'mijia')
    MQTT_PUBLISH_DELAY = os.getenv('MQTT_PUBLISH_DELAY', 300)
    if type(MQTT_PUBLISH_DELAY) == str:
        MQTT_PUBLISH_DELAY = int(MQTT_PUBLISH_DELAY)

    MQTT_SERVER = os.getenv('MQTT_SERVER', '127.0.0.1')

    MQTT_SERVER_PORT = os.getenv('MQTT_SERVER_PORT', 1883)
    if type(MQTT_SERVER_PORT) == str:
        MQTT_SERVER_PORT = int(MQTT_SERVER_PORT)
    MQTT_SERVER_KEEPALIVE = os.getenv('MQTT_SERVER_KEEPALIVE', 60)
    if type(MQTT_SERVER_KEEPALIVE) == str:
        MQTT_SERVER_KEEPALIVE = int(MQTT_SERVER_KEEPALIVE)

    MQTT_USER = os.getenv('MQTT_USER', None)
    MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', None)
    
    HCI_DEV_NO = os.getenv('HCI_DEV_NO', 0)

    MQTT_BASE_TOPIC = os.getenv('MQTT_BASE_TOPIC', 'mijia')

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', help='config file name', type=str, required=True)
    args = parser.parse_args()

    try:
        f = open(args.config)
        # r = f.read()
        j = json.load(f)
        f.close()
    except IOError:
        print("Error reading file: " + args.config)
        return

    comm = MyCommClass()

    while True:
        comm.do_comm()
        time.sleep(60)


if __name__ == '__main__':
    print('Starting MiJia GATT client')
    main()
