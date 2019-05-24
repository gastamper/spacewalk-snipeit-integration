#!/usr/bin/python36
import xmlrpc.client as xc
import re, requests
from sys import exit, exc_info

config = configparser.ConfigParser()
config['DEFAULT'] = {'SATELLITE_URL': "https://your_satellite_url",
                     'SATELLITE_LOGIN': "username",
                     'SATELLITE_PASSWORD': "password"}
config.read('config.ini')

SATELLITE_URL = config['DEFAULT']['SATELLITE_URL']
SATELLITE_LOGIN = config['DEFAULT']['SATELLITE_LOGIN']
SATELLITE_PASSWORD = config['DEFAULT']['SATELLITE_PASSWORD']

#Populate a list of systems from Spacewalk
with xc.Server(SATELLITE_URL, verbose=0) as client:
  try:
    key = client.auth.login(SATELLITE_LOGIN, SATELLITE_PASSWORD)
    query = client.system.listSystems(key)
  except:
    logger.error("Error connecting to Spacewalk: %s" % exc_info()[1])
    exit(1)
system = query[0]
if system:
    for item in 'id','name','last_checkin':
        print("%s: %s" % (item, system[item]))
    print("CPU: ")
    for k,val in client.system.getCpu(key, system['id']).items():
        print("\t%s: %s" % (k, val))
    print("Memory: ")
    for k,val in client.system.getMemory(key, system['id']).items():
        print("\t%s: %s" % (k, val))
    print("Details: ")
    for k,val in client.system.getDetails(key, system['id']).items():
        print("\t%s: %s" % (k, val))
    print("Network: ")
    for k,val in client.system.getNetwork(key, system['id']).items():
        print("\t%s: %s" % (k, val))
# Get DMI information
    print("DMI: ")
    for k,val in client.system.getDmi(key, system['id']).items():
        print("\t%s: %s" % (k, val))
    exit(1)
    client.auth.logout(key)
