#!/usr/bin/python36
import requests, json, configparser
from sys import argv, exit

config = configparser.ConfigParser()
config['DEFAULT'] = {'SNIPE_URL': "https://your_snipe_url/",
                     'API_TOKEN': "YOUR_SNIPE_API_TOKEN_HERE"}
config.read('config.ini')
queries = [ "hardware", "categories", "models", "licenses", "manufacturers", "fieldsets", "users" ]

def error():
    print("Syntax: %s <query_type> [asset]" % argv[0])
    print("Supported query types: %s" % (', '.join(map(str, queries))))
    exit(1)

if len(argv) is 1 or argv[1] not in queries: error()
search = argv[2] if len(argv)>2 else ''

querystring = {"offset":"0","search":argv[2] if len(argv)>2 else ""}
headers = { 'authorization': "Bearer " + config['DEFAULT']['API_TOKEN'], 'accept': "application/json", 'content-type': "application/json" }
querytype = "".join([ x for x in argv[1] if argv[1] in queries])
id = requests.request("GET", config['DEFAULT']['SNIPE_URL'] + "/api/v1/" + querytype, headers=headers, params=querystring)

js = json.loads(id.text)
iteration = 0
if 'error' in js.keys():
    print('Error: %s' % js['error'])
    exit(2)
if js['total'] != 0:
    for i in range(len(js['rows'])):
        # Snipe's API call returns all fieldsets, so filter out those unrelated to query
        if search not in js['rows'][i]['name']: 
            continue
        iteration += 1
        print("Result #%s" % iteration)
        print(json.dumps(js['rows'][i], indent=2,sort_keys=False))
    print("\r\nTotal results: %s" % iteration)
else:
    if len(argv)>2:
        print("%s doesn't exist in Snipe %s" % (argv[2], argv[1]))
    else:
        print("No entries in Snipe category %s" % argv[1])

