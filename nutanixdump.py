#!/usr/bin/env python36
import requests, base64, json, configparser
from sys import exit, argv

if __name__ == "__main__":
    config = configparser.ConfigParser()
    config['DEFAULT'] = { 'NUTANIX_HOST': "https://nutanix:9440",
                          'NUTANIX_USERNAME': "username",
                          'NUTANIX_PASSWORD': "password" }
    config.read('config.ini')

    NUTANIX_HOST = config['DEFAULT']['NUTANIX_HOST']
    NUTANIX_USERNAME = config['DEFAULT']['NUTANIX_USERNAME']
    NUTANIX_PASSWORD = config['DEFAULT']['NUTANIX_PASSWORD']


    payload = "{\"kind\":\"vm\"}"
    hashi = "%s:%s" % (NUTANIX_USERNAME, NUTANIX_PASSWORD)
    base64string = base64.encodestring(hashi.encode("utf-8"))
    headers = { 'content-type': "application/json",
                'authorization': "Basic %s" % base64string.decode("utf-8").replace('\n','') }
    try: 
        conn = requests.request("POST", NUTANIX_HOST + "/api/nutanix/v3/vms/list", data=payload, headers=headers)
    except:
        print("Error connecting to Nutanix: %s" % exc_info()[1])
        exit(1)
    js = json.loads(conn.text)
    if len(argv) is 1:
        print(json.dumps(js, indent=2))
    else:
        for item in js['entities']:
            if item['status']['name'] == argv[1]:
                print(json.dumps(item, indent=2))
