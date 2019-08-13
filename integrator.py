#!/usr/bin/env python36
import xmlrpc.client as xc
import re, requests, json, configparser, base64, logging
from datetime import datetime
from sys import exit, exc_info
from optparse import OptionParser

parser = OptionParser()
parser.add_option("-t", "--test", dest="test", action="store_true", default=False, help="test on a single Spacewalk machine")
parser.add_option("-s", "--skip-spacewalk", dest="skipspacewalk", action="store_true", default=False, help="skip Spacewalk portion")
parser.add_option("-n", "--skip-nutanix", dest="skipnutanix", action="store_true", default=False, help="skip Nutanix portion")
parser.add_option("-v", "--verbose", dest="verbose", action="store_true", default=False, help="enable verbose logging")
(options, args) = parser.parse_args()


updated, skipped = ([],[])
# Function to search and return a Snipe data for an item
def snipesearch(name):
     querystring = {"offset":"0","search":str(name)}
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
     return js

# Function to perform an update to an existing asset entry in Snipe
def patch(snipeid, item, data):
    payload = "{\"%s\":\"%s\"}" % (str(item), str(data))
    patch = requests.request("PATCH", SNIPE_URL + "/" + str(snipeid), headers=headers, data=payload)
    newjs = json.loads(patch.text)
    if newjs['status'] != 'error':
        logger.debug(f"Updated Snipe asset number {snipeid}, field {str(item)} with {str(data)}")
    # Track updates by returning 1, unfortunately
        return 1
    else: 
        logger.error(f"Failed to update Snipe asset number {snipeid}: {newjs['messages']}")
        return 0

# Function to create a new entry in Snipe from Spacewalk data
def post(item, payload, item_name):
    patch = requests.request("POST", SNIPE_URL , headers=headers, data=payload)
    newjs = json.loads(patch.text)
    if newjs['status'] != 'error':
        logger.debug(f"Created new Snipe asset, field {str(item)} with {str(payload)}")
    else:
        logger.error(f"Failed to create new Snipe asset: {newjs['messages']}")
        return 1
    patch = requests.request("PATCH", SNIPE_URL + "/" + str(newjs['payload']['id']), headers=headers, data="{\"name\":\"" + item_name + "\"}")
    newjs = json.loads(patch.text)
    if newjs['status'] != 'error':
        return 0
    else:
        logger.error(f"Couldn't update new asset item name: {newjs['messages']}")
        return 1

# Function to compare Snipe and Spacewalk data and initiate updates if necessary
def update_item(system):
# Basic info    
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
        split = centospkg[0]['release'].split('.')
        if len(split) == 5:
            minor, release, what, version, arch = split
        elif len(split) == 4:
            minor, release, version, arch = split
        else:
            logger.error("Couldn't parse CentOS package version")
            minor, release, version, arch = [0,0,0,"centos"]
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
    systemitem['model'] = dmi['product']
    # Pull and fix serial tag formatting, skip any secondary regex matches, etc
    # We are only pulling chassis serial; if board is necessary, change below
    systemitem['serial'] = dmi['asset']
    systemitem['serial'] = str(re.findall("(?<=\(chassis: )\w+\)", systemitem['serial']))
    # In case of multiple regex returns
    if isinstance(systemitem['serial'], list): 
        systemitem['serial'] = systemitem['serial'][0].strip('[]\' ')[:-1]
    else: 
        systemitem['serial'] = systemitem['serial'].partition(")")[0].strip("[]\' ")
    # Validate if chassis happened to be "empty" but we have a system tag, f.e. TYAN systems
    if systemitem['serial'] == "empty":
        systemitem['serial'] = dmi['asset']
        systemitem['serial'] = str(re.findall("(?<=\(system: )\w+\)", systemitem['serial'])).strip("\'[])")

### Snipe section
    js = snipesearch(str(system['name']))
    if 'total' in js and js['total'] == 1:
      snipeid = js['rows'][0]['id']
    else: 
        snipeid = "Unknown"
        logger.debug(f"Couldn't find {systemitem['name']} in Snipe")
# Populate asset tag on Snipe side
# This section will require changes for any variations on hostname/asset tag setup
#CONFIG1
    if systemitem['name'][:4] == "lxd-" or systemitem['name'][:4] == "lxl-":
        systemitem['asset_tag'] = systemitem['name'][4:]
    else: systemitem['asset_tag'] = systemitem['name']
    type = systemitem['name'][:3]
#CONFIG2
    systemitem['model'] = dmi['product']
    if type == "lxd":
        systemitem['category'] = {'id':50, 'name':'Managed Linux Desktop'}
        systemitem['fieldset_id'] = 3
    elif type == "lxl":
        systemitem['category'] = {'id':79, 'name':'Managed Linux Laptop'}
        systemitem['fieldset_id'] = 3
    else:
        systemitem['category'] = {'id':77, 'name':'Science Servers'}
        systemitem['fieldset_id'] = 2

    # Required Snipe fields are asset tag, model, and status.
    # Assume anything extant in Spacewalk is ready to deploy
    # TODO: move this to new addition section.
    systemitem['status_label'] = "Ready to Deploy"
    systemitem['status_labelid'] = 2
   
# Only attempt patching on existing entries in Snipe
    if snipeid != "Unknown":
        snipedata = js['rows'][0]
        logger.info(f"Checking system {systemitem['name']}")
    # Update default fields in Snipe
    # In practice, asset tags should always match
        if snipedata['asset_tag'] != systemitem['asset_tag'] and systemitem['fieldset_id'] != 2:
                    logger.debug("MISMATCH: Snipe data: %s, Spacewalk data: %s" % (snipedata['asset_tag'], systemitem['asset_tag']))
                    update = patch(str(snipeid), 'asset_tag', systemitem['asset_tag'])
    # Last checkin update
        dtobj = datetime.strptime(str(systemitem['last_checkin']), "%Y%m%dT%H:%M:%S")
        dt = str(dtobj.date()) + " " + str(dtobj.time())
        update = 0
    # Update hostname/item name
        if snipedata['name'] != systemitem['name']:
            update += patch(snipeid, 'name', systemitem['name'])
    # Update custom fields in Snipe
#CONFIG3
        if snipedata['custom_fields']['Operating System']['value'] != systemitem['release']:
            update += patch(snipeid, '_snipeit_operating_system_12', systemitem['release'])
        if snipedata['custom_fields']['IP Address']['value'] != systemitem['ip']:
            update += patch(snipeid, '_snipeit_ip_address_40', systemitem['ip'])
        # Some values set in Snipe don't return as ints until they have data; or clause addresses that
        if not snipedata['custom_fields']['Total RAM']['value'] or \
            int(snipedata['custom_fields']['Total RAM']['value']) != int(systemitem['ram']):
            update += patch(snipeid, '_snipeit_total_ram_20', systemitem['ram'])
        if not snipedata['custom_fields']['Total CPU']['value'] or \
            int(snipedata['custom_fields']['Total CPU']['value']) != int(systemitem['socket_count']):
            update += patch(snipeid, '_snipeit_total_cpu_18', systemitem['socket_count'])
        if not snipedata['custom_fields']['Total Cores']['value'] or \
            int(snipedata['custom_fields']['Total Cores']['value']) != int(systemitem['count']):
            update += patch(snipeid, '_snipeit_total_cores_19', systemitem['count'])
        if systemitem['fieldset_id'] == 2:
            packagelist = client.system.listPackages(key, systemitem['id'])
            for item in packagelist:
                if item['name'] == 'gpfs.base':
                    logger.debug("Found GPFS package")
#            if not snipedata['custom_fields']['GPFS Client']

# For recording when a machine last checked in with Spacewalk; will balloon SnieIT item history significantly.
#        if snipedata['custom_fields']['Last Checkin']['value'] != dt:
#            update = patch(snipeid, '_snipeit_last_checkin_39', dt)
        # Spacewalk agent < version 2.9 has a bug on line 86 of hardware.py, uncomment below to skip DMI info on these machines
#        if not centospkg: 
#            logger.debug("Skipping DMI information check on AMD64 machine %s" % (systemitem['name']))
        if snipedata['serial'] != systemitem['serial']:
            update += patch(snipeid, 'serial', systemitem['serial'])
        if update != 0: 
            if systemitem['name'] not in updated: updated.append(systemitem['name'])
            logger.info(f"Updated {systemitem['name']}")
        # Check if manufacturer exists; add if not
        querystring = {"search":systemitem['vendor']}
        ret = requests.request("GET", config['DEFAULT']['SNIPE_URL'] + "/api/v1/manufacturers", headers=headers,params=querystring)
        js = json.loads(ret.text)
        if js['total'] == 0:
            logger.info("Vendor %s not found, adding to Snipe" % systemitem['vendor'])
            querystring = {"name":systemitem['vendor']}
            addvendor = requests.request("POST",  config['DEFAULT']['SNIPE_URL'] + "/api/v1/manufacturers", headers=headers,params=querystring)
            addvendor = json.loads(addvendor.text)
            if addvendor['status'] == 'error':
                logger.error('Failed to add manufacturer: %s' % addvendor['messages'])
                exit(2)
            vendorid = addvendor['payload']['id']
        else:
            for item in js['rows']:
                if item['name'] == systemitem['vendor']:
                    vendorid = item['id']
                    logger.debug("Got manufacturer id %s" % vendorid)
        # Check if model exists; add if not
        querystring = {"search":systemitem['model']}
        ret = requests.request("GET", config['DEFAULT']['SNIPE_URL'] + "/api/v1/models", headers=headers,params=querystring)
        js = json.loads(ret.text)
        if js['total'] == 0:
            logger.info("Model %s not found, adding to Snipe" % systemitem['model'])
            querystring = {"name":systemitem['model'],"category_id":systemitem['category']['id'],"manufacturer_id":vendorid,"fieldset_id":systemitem['fieldset_id']}
            addmodel = requests.request("POST",  config['DEFAULT']['SNIPE_URL'] + "/api/v1/models", headers=headers,params=querystring)
            addmodel = json.loads(addmodel.text)
            if addmodel['status'] == 'error':
                logger.error('Failed to add model: %s' % addmodel['messages'])
                exit(2)
            logger.debug(addmodel)
            systemitem['model_id'] = addmodel['payload']['id']
        else:
            for item in js['rows']:
                if item['name'] == systemitem['model']:
                    systemitem['model_id'] = item['id']
                    logger.debug("Got model id %s" % item['id'])
        # Update model if mismatch
#TODO: Document this for configuration
        # If no model information (Ubuntu), default to below
        if not systemitem['model']:
            systemitem['model'] = 'Linux Desktop'
            systemitem['model_id'] = 67
        # If model returned from dmidecode
        if systemitem['model'] != snipedata['model']['name']:
            patch(snipeid, 'model_id', systemitem['model_id'])
            logger.info("Updated model to %s" % systemitem['model'])


#CONFIG4
# Add new system to Snipe from Spacewalk data    
    else: 
#        systemitem['vendor'] = "testman"
#        systemitem['model'] = "testmodel"
        logger.debug("Attempting to add system not in Snipe")
        payload = "{\"asset_tag\":\"" + systemitem['name'][4:] + "\", \"status_id\":1, \"model_id\":\"67\", \"item_name\": \"" + systemitem['name'] + "\"}"
        #payload = "{\"asset_tag\":\"" + systemitem['name'][4:] + "\", \"status_id\":1, \"model_id\":\"" + str(systemitem['model_id']) + "\", \"item_name\": \"" + systemitem['name'] + "\"}"
        out = post(systemitem['name'], payload, systemitem['name'])
        if out != 1:
            update_item(system)
        elif systemitem['name'] not in skipped: 
            # Update POST failed, so add to skipped
            skipped.append(systemitem['name'])

#TODO snipe update section
# Function to update Spacewalk details for an item
    def spacedetails(id, snipeitem, spaceitem, called):
        try: 
            request = client.system.setDetails(key, id, {spaceitem:snipeitem})
            logger.info(f"Updated {systemitem['name']} with new {called}: {snipeitem}")
            return 1
        except:
            logger.error(f"Failed to update Spacewalk id {id} field {spaceitem}({called}) with {snipeitem}")
            logger.debug(f"Error: {exc_info()}")
            return 0
    # Update owner if item is assigned to someone/where in Snipe
    # Can wind up here on snipeitem = "Unknown"
    if snipeid != "Unknown":
        try:
            if snipedata['assigned_to'] and snipedata['assigned_to']['name'] != systemitem['owner']: 
                logger.debug("Owner mismatch on %s: Snipe has %s, Spacewalk has %s"  % 
                    (systemitem['name'], snipedata['assigned_to']['name'], systemitem['owner']))
                update = spacedetails(systemitem['id'], snipedata['assigned_to']['name'], "description", "name")
            if systemitem['name'] not in updated and update != 0: updated.append(systemitem['name'])
    # Update location if one exists for item in Snipe
            if snipedata['rtd_location'] and snipedata['rtd_location']['name'] != systemitem['location']:
                logger.debug("Location mismatch on %s: Snipe has %s, Spacewalk has %s" %
                    (systemitem['name'], snipedata['rtd_location']['name'], systemitem['location']))
                update = spacedetails(systemitem['id'], snipedata['rtd_location']['name'], "room", "location")
                if systemitem['name'] not in updated and update != 0: updated.append(systemitem['name'])
    # Trap exceptions if Snipe update fails out
        except: 
            logger.debug(f"Snipe field comparison failed: {exc_info()}")
            pass
    
# /for item in systemgroup

if __name__ == "__main__":
# ConfigParser setup
    config = configparser.ConfigParser()
    config['DEFAULT'] = { 'SATELLITE_URL': "https://your_satellite_url",
                          'SATELLITE_LOGIN': "username",
                          'SATELLITE_PASSWORD': "password",
                          'SNIPE_URL': "https://your_snipe_url/",
                          'API_TOKEN': "YOUR_SNIPE_API_TOKEN_HERE",
                          'USE_NUTANIX': False,
                          'NUTANIX_HOST': "https://nutanix:9440",
                          'NUTANIX_USERNAME': "username",
                          'NUTANIX_PASSWORD': "password" }
    config.read('config.ini')

    SNIPE_URL = config['DEFAULT']['SNIPE_URL'] + "/api/v1/hardware"
    SATELLITE_URL = config['DEFAULT']['SATELLITE_URL']
    SATELLITE_LOGIN = config['DEFAULT']['SATELLITE_LOGIN']
    SATELLITE_PASSWORD = config['DEFAULT']['SATELLITE_PASSWORD']
    API_TOKEN = config['DEFAULT']['API_TOKEN']
    NUTANIX_HOST = config['DEFAULT']['NUTANIX_HOST']
    NUTANIX_USERNAME = config['DEFAULT']['NUTANIX_USERNAME']
    NUTANIX_PASSWORD = config['DEFAULT']['NUTANIX_PASSWORD']
    USE_NUTANIX = config.getboolean('DEFAULT', 'USE_NUTANIX')

# Logger setup
    logformatter = logging.Formatter(fmt='[%(asctime)-15s %(levelname)6s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger()
    streamhandler = logging.StreamHandler()
    streamhandler.setFormatter(logformatter)
    logger.addHandler(streamhandler)
    # Turn off urllib3's logging
    for item in [logging.getLogger(name) for name in logging.root.manager.loggerDict]: item.setLevel(logging.WARNING)
    if options.verbose is True:
        logger.setLevel(logging.DEBUG)
    else: logger.setLevel(logging.INFO)

# Set headers for connecting to Snipe
    headers = {'authorization': "Bearer " + API_TOKEN, 'accept': "application/json", 'content-type':"application/json" }

#Populate a list of systems from Spacewalk
    if options.skipspacewalk is False:
        with xc.Server(SATELLITE_URL, verbose=0) as client:
            try:
                key = client.auth.login(SATELLITE_LOGIN, SATELLITE_PASSWORD)
                query = client.system.listSystems(key)
            except:
                logger.error("Error connecting to Spacewalk: %s" % exc_info()[1])
                exit(1)

#  For testing, use a single system
        if options.test is True:
            system = [x for x in query if x["name"] == "lxmgmt"]
            if system:
               update_item(system[0])
               query = system
        else:
# For all Spacewalk systems:
            for system in query:
                update_item(system)
        client.auth.logout(key)

# For Nutanix VMs
    if USE_NUTANIX is True and options.skipnutanix is False:
        hashi = "%s:%s" % (NUTANIX_USERNAME, NUTANIX_PASSWORD)
        base64string = base64.encodestring(hashi.encode("utf-8"))
        nutanixheader = { 'content-type': "application/json",
                    'authorization': "Basic %s" % base64string.decode("utf-8").replace('\n','') }
        payload= "{\"kind\":\"vm\"}"
        try:
            conn = requests.request("POST", NUTANIX_HOST + "/api/nutanix/v3/vms/list", data=payload, headers=nutanixheader)
        except:
            logger.error("Error connecting to Nutanix: %s" % exc_info()[1])
            exit(1)
        njs = json.loads(conn.text)
        update = 0 
        if 'entities' in njs:
            for entity in njs['entities']:
#                print(f"{entity['status']['name']}: {entity['status']['resources']['num_sockets']} sockets x{entity['status']['resources']['num_vcpus_per_socket']} CPU per, {entity['status']['resources']['memory_size_mib']}Mb RAM")
                njsdata = snipesearch(entity['metadata']['uuid'])
# Snipe returns 0 for total if no returns, thus new system
                if 'total' in njsdata and njsdata['total'] == 0:
                    logger.info(f"Adding new item {entity['status']['name']} to Snipe")
                    payload = "{\"asset_tag\":\"" + entity['status']['name'] + "\", \"status_id\":1, \"model_id\":\"88\", \"item_name\": \"" + entity['status']['name'] + "\"}"
                    if post(entity['status']['name'], payload, entity['status']['name']) == 1:
                        logger.error(f"Failed to add {entity['status']['name']} to Snipe")
                        continue
                elif 'total' not in njsdata:
                    logger.error(f"Something broke querying Snipe")
                    logger.debug(f"{njsdata}")
                    exit(1)
                    
                snipedata = snipesearch(entity['status']['name'])
                if 'rows' in snipedata and snipedata['rows'][0]:
                    snipedata = snipedata['rows'][0]
                else:
                    logger.error("Something broke querying snipe and no rows were returned")
                snipeid = snipedata['id']
                if not snipedata['custom_fields']['Total RAM']['value'] or \
                    int(snipedata['custom_fields']['Total RAM']['value']) != int(entity['status']['resources']['memory_size_mib']):
                    update += patch(snipeid, '_snipeit_total_ram_20', int(entity['status']['resources']['memory_size_mib']))
                if not snipedata['custom_fields']['Total CPU']['value'] or \
                    int(snipedata['custom_fields']['Total CPU']['value']) != int(entity['status']['resources']['num_sockets']):
                    update += patch(snipeid, '_snipeit_total_cpu_18', int(entity['status']['resources']['num_sockets']))
                if not snipedata['custom_fields']['Total Cores']['value'] or \
                    int(snipedata['custom_fields']['Total Cores']['value']) != int(entity['status']['resources']['num_vcpus_per_socket']):
                    update += patch(snipeid, '_snipeit_total_cores_19', int(entity['status']['resources']['num_vcpus_per_socket']))
                if not snipedata['custom_fields']['UUID']['value'] or \
                    snipedata['custom_fields']['UUID']['value'] != str(entity['metadata']['uuid']):
                    update += patch(snipeid, '_snipeit_uuid_41', entity['metadata']['uuid'])
                # Default to deployable status ID
                # TODO breakout to separate post_location function or otherwise support error handling
                if snipedata['status_label']['id'] != 2:
                    update += patch(snipeid, 'status_id', 2)
                # Checkout directly to Datacenter location
                if snipedata['assigned_to'] is None:
                    patch = requests.request("POST", SNIPE_URL + "/" + str(snipeid) + "/checkout", headers=headers, data="{\"checkout_to_type\":\"location\",\"assigned_location\":16}")
            logger.debug("%s Nutanix VMs reported." % len(njs['entities']))
        elif 'state' in njs:
            for item in njs['message_list']:
                logger.debug("Error communicating with Nutanix: %s: %s" % ( njs['code'], item['message']))

# Report final data tallies
    # If Spacewalk is skipped, query is empty
    try: query
    except: query = []
    logger.info("%s total: %s skipped, %s updated, %s unchanged" % (len(query), len(skipped), len(updated), len(query) - len(updated)))
    exit(0)
