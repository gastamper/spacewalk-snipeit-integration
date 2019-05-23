#!/usr/bin/python36
import requests, json, configparser
from sys import argv

config = configparser.ConfigParser()
config['DEFAULT'] = {'SNIPE_URL': "https://your_snipe_url/",
                     'API_TOKEN': "YOUR_SNIPE_API_TOKEN_HERE"}
config.read('config.ini')

querystring = {"limit":"1","offset":"0","search":argv[1]}
headers = { 'authorization': "Bearer " + config['DEFAULT']['API_TOKEN'], 'accept': "application/json", 'content-type': "application/json" }
id = requests.request("GET", config['DEFAULT']['SNIPE_URL'] + "/api/v1/hardware", headers=headers, params=querystring)

js = json.loads(id.text)
if js['total'] != 0:
    for key, value in js['rows'][0].items():
        print("%s: %s" % (key, value))
else:
    print("Item %s doesn't exist in Snipe" % argv[1])
