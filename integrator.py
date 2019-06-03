#!/usr/bin/python36
import xmlrpc.client as xc
import re, requests, json, configparser
import logging
from sys import exit, exc_info

config = configparser.ConfigParser()
config['DEFAULT'] = {'SATELLITE_URL': "https://your_satellite_url",
                     'SATELLITE_LOGIN': "username",
                     'SATELLITE_PASSWORD': "password",
                     'SNIPE_URL': "https://your_snipe_url/",
                     'API_TOKEN': "YOUR_SNIPE_API_TOKEN_HERE"}
config.read('config.ini')

SNIPE_URL = config['DEFAULT']['SNIPE_URL'] + "/api/v1/hardware"
SATELLITE_URL = config['DEFAULT']['SATELLITE_URL']
SATELLITE_LOGIN = config['DEFAULT']['SATELLITE_LOGIN']
SATELLITE_PASSWORD = config['DEFAULT']['SATELLITE_PASSWORD']
API_TOKEN = config['DEFAULT']['API_TOKEN']
headers = {'authorization': "Bearer " + API_TOKEN, 'accept': "application/json", 'content-type':"application/json" }
updated, skipped = ([],[])

# Logger setup
logformatter = logging.Formatter(fmt='[%(asctime)-15s %(levelname)6s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger()
streamhandler = logging.StreamHandler()
streamhandler.setFormatter(logformatter)
logger.addHandler(streamhandler)
logger.setLevel(logging.DEBUG)
# Turn off urllib3's logging
for item in [logging.getLogger(name) for name in logging.root.manager.loggerDict]: item.setLevel(logging.WARNING)
logger.setLevel(logging.DEBUG)

# Function to perform an update to an existing asset entry in Snipe
def patch(snipeid, item, data):
    payload = "{\"%s\":\"%s\"}" % (str(item), str(data))
    patch = requests.request("PATCH", SNIPE_URL + "/" + str(snipeid), headers=headers, data=payload)
    newjs = json.loads(patch.text)
    if newjs['status'] != 'error':
      logger.debug(f"Updated Snipe asset number {snipeid}, field {str(item)} with {str(data)}")
      return 0
    else: 
      logger.error(f"Failed to update Snipe asset number {snipeid}: {newjs['messages']}")
      return 1
# Function to create a new entry in Snipe from Spacewalk data
def post(item, payload):
    #payload = "{\"%s\":\"%s\"}" % (str(item), str(data))
    patch = requests.request("POST", SNIPE_URL , headers=headers, data=payload)
    newjs = json.loads(patch.text)
    if newjs['status'] != 'error':
      logger.debug(f"Created new Snipe asset, field {str(item)} with {str(payload)}")
      return 0
    else:
      logger.error(f"Failed to create new Snipe asset: {newjs['messages']}")
      return 1

# Function to compare Snipe and Spacewalk data and initiate updates if necessary
def update_item(system):
# Basic info    
    global unchanged
    global updated
    global skipped
    systemitem = {}
    systemitem['id'] = system["id"]
    systemitem['name'] = system["name"]
    systemitem['last_checkin'] = system["last_checkin"]
# CPU info
    cpu = (client.system.getCpu(key, systemitem['id']))
    systemitem['count'] = cpu['count']
    systemitem['mhz'] = cpu['mhz']
    # socket_count is apparently unpopulated if single socket
    if "socket_count" in cpu:
       systemitem['socket_count'] = cpu['socket_count']
    else: systemitem['socket_count'] = "1"
# Memory info
    ram = (client.system.getMemory(key, systemitem['id']))
    systemitem['ram'] = ram['ram']
    systemitem['swap'] = ram['swap']
# Details info
    details = (client.system.getDetails(key, systemitem['id']))
    systemitem['owner'] = details['description']
    systemitem['location'] = details['building'] + details['room']
    systemitem['release'] = details['release']
# Get CentOS release package information
    packages = (client.system.listPackages(key, systemitem['id']))
    # Report CentOS and Ubuntu versions differently
    centospkg = [ x for x in packages if x["name"] == "centos-release" ]
    if centospkg:
        minor, release, what, version, arch = centospkg[0]['release'].split('.')
        # Strip 'el' prepending release and capitalize arch
        version = re.sub('[^0-9]','',version)
        if arch == "centos": arch = "CentOS"
        systemitem['release'] = arch + " " + version + "." + minor + "." + release
    # Fix release reporting if Ubuntu
    if "bionic" in systemitem['release'] or "xenial" in systemitem['release']:
        systemitem['release'] = "Ubuntu " + systemitem['release']
# Get network information
    network = (client.system.getNetwork(key, systemitem['id']))
    systemitem['ip'] = network['ip']
# Get DMI information
    dmi = (client.system.getDmi(key, systemitem['id']))
    systemitem['vendor'] = dmi['vendor']
    # Pull and fix serial tag formatting, skip any secondary regex matches, etc
    systemitem['serial'] = dmi['asset']
    systemitem['serial'] = str(re.findall("(?<=\(chassis: )\w+\)", systemitem['serial']))
    # In case of multiple regex returns
    if isinstance(systemitem['serial'], list): 
        systemitem['serial'] = systemitem['serial'][0]
        systemitem['serial'] = systemitem['serial'].strip('[]\' ')[:-1]
    else: 
        systemitem['serial'] = systemitem['serial'].partition(")")[0].strip("\'[")
        systemitem['serial'] = systemitem['serial'].strip('[]\' ')
    # Validate if chassis happened to be empty but we have a system tag
    #TODO make this less terrible
    if systemitem['serial'] == "empty":
        systemitem['serial'] = dmi['asset']
        systemitem['serial'] = str(re.findall("(?<=\(system: )\w+\)", systemitem['serial'])).strip("\'[])")
### Snipe section
# Get Snipe ID
    querystring = {"offset":"0","search":str(system['name'][4:])}
    try: id = requests.request("GET", SNIPE_URL, headers=headers, params=querystring)
    except:
        logger.error("Error connecting to Snipe: %s" % exc_info()[1])
        exit(1)
    js = json.loads(id.text)
    if 'error' in js:
        if js['error'] == 'Unauthorized.':
            logger.error("Error from Snipe: Unauthorized (check API key)")
        else: logger.error("Error from Snipe: %s" % js['error'])
        exit(1)
    if 'total' in js and js['total'] == 1:
      snipeid = js['rows'][0]['id']
    else: snipeid = "Unknown"
# Populate asset tag on Snipe side
    systemitem['asset_tag'] = systemitem['name'][4:]
    type = systemitem['name'][:3]
    if type == "lxd":
        systemitem['model'] = {'id':67,'name':'Linux Desktop'}
        systemitem['category'] = {'id':50, 'name':'Managed Linux Desktop'}
    elif type == "lxl":
        systemitem['model'] = {'id':68, 'name':'Linux Laptop'}
        systemitem['category'] = {'id':79, 'name':'Managed Linux Laptop'}
    else:
        logger.debug("Couldn't deetrmine model or category from hostname")
    # Required Snipe fields are asset tag, model, and status.
    # Assume anything extant in Spacewalk is ready to deploy
    systemitem['status_label'] = "Ready to Deploy"
    systemitem['status_labelid'] = 2
   
# Only attempt patching on existing entries in Snipe
    if snipeid != "Unknown":
        snipedata = js['rows'][0]
    # location requires preknown location id
    # These require no foreknowledge
        for item in ('asset_tag', 'model'):
            if snipedata[item] != systemitem[item]:
                    logger.debug("MISMATCH: snipe data: %s, spacewalk data: %s" % (snipedata[item], systemitem[item]))
                    update = patch(str(snipeid), item, systemitem[item])
        from datetime import datetime
        dtobj = datetime.strptime(str(systemitem['last_checkin']), "%Y%m%dT%H:%M:%S")
        dt = str(dtobj.date()) + " " + str(dtobj.time())
        update = 0
        if snipedata['name'] != systemitem['name']:
            update = patch(snipeid, 'name', systemitem['name'])
        if snipedata['custom_fields']['Operating System']['value'] != systemitem['release']:
            update = patch(snipeid, '_snipeit_operating_system_12', systemitem['release'])
        if snipedata['custom_fields']['IP Address']['value'] != systemitem['ip']:
            update = patch(snipeid, '_snipeit_ip_address_40', systemitem['ip'])
        if not snipedata['custom_fields']['Total RAM']['value'] or \
            int(snipedata['custom_fields']['Total RAM']['value']) != int(systemitem['ram']):
            update = patch(snipeid, '_snipeit_total_ram_20', systemitem['ram'])
        if not snipedata['custom_fields']['Total CPU']['value'] or \
            int(snipedata['custom_fields']['Total CPU']['value']) != int(systemitem['socket_count']):
            update = patch(snipeid, '_snipeit_total_cpu_18', systemitem['socket_count'])
        if not snipedata['custom_fields']['Total Cores']['value'] or \
            int(snipedata['custom_fields']['Total Cores']['value']) != int(systemitem['count']):
            update = patch(snipeid, '_snipeit_total_cores_19', systemitem['count'])
# Disabled while debugging
#        if snipedata['custom_fields']['Last Checkin']['value'] != dt:
#            update = patch(snipeid, '_snipeit_last_checkin_39', dt)
        # Ubuntu spacewalk agent doesn't pull dmidecode information so skip empty entriesi
        if not centospkg: 
            logger.debug("Skipping DMI information check on AMD64 machine %s" % (systemitem['name']))
        elif snipedata['serial'] != systemitem['serial']:
            update = patch(snipeid, 'serial', systemitem['serial'])
        if update != 0: 
            if systemitem['name'] not in updated: updated.append(systemitem['name'])
            logger.info(f"Updated {systemitem['name']}")
#        else: unchanged += 1
# Add new system to Snipe from Spacewalk data    
    else: 
        logger.debug("Attempting to add system not in Spice")
        payload = "{\"asset_tag\":\"" + systemitem['name'][4:] + "\", \"status_id\":1, \"model_id\":67, \"item_name\": \"" + systemitem['name'] + "\"}"
        if (post(systemitem['name'], payload)) != 1:
            update_item(system)
        elif systemitem['name'] not in skipped: skipped.append(systemitem['name'])

#TODO snipe update section
    try: 
      if snipedata['assigned_to']['name'] != systemitem['owner']: 
          logger.debug("Owner mismatch on %s: Snipe says %s, Spacewalk has %s " % (systemitem['name'], snipedata['assigned_to']['name'], systemitem['owner']))
          try: 
            request = client.system.setDetails(key, systemitem['id'], {"description":snipedata['assigned_to']['name']})
            logger.info(f"Updated {systemitem['name']} with new owner {snipedata['assigned_to']['name']}")
            if systemitem['name'] not in updated: updated.append(systemitem['name'])
          except:
            logger.error(f"XMLRPC returned error setting new user on {systemitem['name']}")
      else: pass
    except: pass
        
# Format up and print data from this iteration
    id = systemitem

#    logger.info(f"{id['name']}: {id['owner']}, {id['location']}, {id['release']}, {id['count']} core, {id['socket_count']} socket, {id['mhz']} mhz, {id['ram']} RAM, {id['swap']} swap, serial {id['serial'] if id['serial'] else 'empty'}, address {id['ip']}, snipeid {snipeid}") 
    # /for item in systemgroup
#Populate a list of systems from Spacewalk
with xc.Server(SATELLITE_URL, verbose=0) as client:
  try:
    key = client.auth.login(SATELLITE_LOGIN, SATELLITE_PASSWORD)
    query = client.system.listSystems(key)
  except:
    logger.error("Error connecting to Spacewalk: %s" % exc_info()[1])
    exit(1)
#system = [x for x in query if x["name"] == "lxd-02010974"]
#if system:
#    update_item(system[0])
#    query =  system
for system in query:
    update_item(system)
# Report final data tallies
logger.info("%s total: %s skipped, %s updated, %s unchanged" % (len(query), len(skipped), len(updated), len(query) - len(updated)))
client.auth.logout(key)
