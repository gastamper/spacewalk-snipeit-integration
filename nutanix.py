#!/usr/bin/env python36
import xmlrpc.client as xc
import re, requests, json, configparser, base64, logging
from datetime import datetime
from sys import exit, exc_info
from optparse import OptionParser

parser = OptionParser()
parser.add_option("-t", "--test", dest="test", action="store", default=False, help="test on a single Spacewalk machine")
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

if __name__ == "__main__":
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
    CUSTOM_FIELDS = config.getboolean('SNIPE', 'CUSTOM_FIELDS')
    try: DEFAULT_FIELDSET = config.getint('SNIPE', 'DEFAULT_FIELDSET')
    except:
        logger.error("DEFAULT_FIELDSET must be an integer")
        exit(1)
    try: DEFAULT_CATEGORY = config.getint('SNIPE', 'DEFAULT_CATEGORY')
    except:
        logger.error("DEFAULT_CATEGORY must be an integer")
        exit(1)

    headers = {'authorization': "Bearer " + API_TOKEN, 'accept': "application/json", 'content-type':"application/json" }

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
        if 'entities' in njs:
            for entity in njs['entities']:
                update = 0
                found = 0 
#                print(f"{entity['status']['name']}: {entity['status']['resources']['num_sockets']} sockets x{entity['status']['resources']['num_vcpus_per_socket']} CPU per, {entity['status']['resources']['memory_size_mib']}Mb RAM")
                njsdata = snipesearch(entity['status']['name'])
                logger.debug(f"Searched for {entity['status']['name']}")
# Snipe doesn't do exact matches on search, so filter out names which aren't an exact match
                for item in njsdata['rows']:
                    if item['name'] == entity['status']['name']:
                        founditem = item
                        found = 1
                        continue
                if found == 0:
                    logger.error(f"Couldn't find match: {entity['status']['name']}, new asset")
# Snipe returns 0 for total if no returns, thus new system
                if 'total' in njsdata and njsdata['total'] == 0:
                    logger.info(f"Adding new item {entity['status']['name']} to Snipe")
                    payload = "{\"asset_tag\":\"" + entity['status']['name'] + "\", \"status_id\":1, \"model_id\":\"88\", \"item_name\": \"" + entity['status']['name'] + "\"}"
                    if post(entity['status']['name'], payload, entity['status']['name']) == 1:
                        logger.error(f"Failed to add {entity['status']['name']} to Snipe")
                        continue
                    if entity['metadata']['uuid'] not in updated: updated.append(entity['metadata']['uuid'])
                elif 'total' not in njsdata:
                    logger.error(f"Something broke querying Snipe")
                    logger.debug(f"{njsdata}")
                    exit(1)
                sniped = snipesearch(entity['status']['name'])
# If we just added a new entry, replace old founditem entry with new one
                for entry in sniped['rows']:
                    if entry['name'] == entity['status']['name']:
                        founditem = entry
                logger.info(f"Checking Nutanix VM {entity['metadata']['uuid']}: {entity['status']['name']}")    
#                snipedata = snipesearch(entity['status']['name'])
                snipedata = founditem
#                if 'rows' in snipedata and len(snipedata['rows']) != 0:
#                    snipedata = snipedata['rows'][0]
#                else:
#                    logger.error("Something broke querying snipe and no rows were returned")
#                    exit(1)
                snipeid = snipedata['id']
                if not snipedata['custom_fields']['UUID']['value'] or \
                    snipedata['custom_fields']['UUID']['value'] != str(entity['metadata']['uuid']):
                    update += patch(snipeid, '_snipeit_uuid_41', entity['metadata']['uuid'])
                if not snipedata['custom_fields']['Total RAM']['value'] or \
                    int(snipedata['custom_fields']['Total RAM']['value']) != int(entity['status']['resources']['memory_size_mib']):
                    update += patch(snipeid, '_snipeit_total_ram_20', int(entity['status']['resources']['memory_size_mib']))
                if not snipedata['custom_fields']['Total CPU']['value'] or \
                    int(snipedata['custom_fields']['Total CPU']['value']) != int(entity['status']['resources']['num_sockets']):
                    update += patch(snipeid, '_snipeit_total_cpu_18', int(entity['status']['resources']['num_sockets']))
                if not snipedata['custom_fields']['Total Cores']['value'] or \
                    int(snipedata['custom_fields']['Total Cores']['value']) != int(entity['status']['resources']['num_vcpus_per_socket']):
                    update += patch(snipeid, '_snipeit_total_cores_19', int(entity['status']['resources']['num_vcpus_per_socket']))
                if 'guest_tools' in entity['status']['resources'] and CUSTOM_FIELDS is True:
                    logger.debug("Found NGT")
                    # If NGT is installing or hasn't polled yet, guest_tools can exist without being populated
                    if 'guest_os_version' in entity['status']['resources']['guest_tools']['nutanix_guest_tools']:
                    # This works for CentOS at least, untested with others
                        osver = "".join(entity['status']['resources']['guest_tools']['nutanix_guest_tools']['guest_os_version'].split(":",2)[2].split("Linux-"))
                        if not snipedata['custom_fields']['Operating System']['value'] or \
                            snipedata['custom_fields']['Operating System']['value'] != osver:
                            logger.debug(f"Adding OS info: {osver}")
                            update += patch(snipeid, config['SNIPE']['OPERATING_SYSTEM'], osver)
                # Default to deployable status ID
                # TODO breakout to separate post_location function or otherwise support error handling
                if snipedata['status_label']['id'] != 2:
                    update += patch(snipeid, 'status_id', 2)
                # Checkout directly to Datacenter location
                if snipedata['assigned_to'] is None:
                    patch = requests.request("POST", SNIPE_URL + "/" + str(snipeid) + "/checkout", headers=headers, data="{\"checkout_to_type\":\"location\",\"assigned_location\":16}")
                if entity['metadata']['uuid'] not in updated and update != 0: updated.append(entity['metadata']['uuid'])
                logger.debug(f"Done with {entity['status']['name']}")
            logger.info("%s Nutanix VMs reported." % len(njs['entities']))
        elif 'state' in njs:
            for item in njs['message_list']:
                logger.debug("Error communicating with Nutanix: %s: %s" % ( njs['code'], item['message']))

# Report final data tallies
    # If Spacewalk is skipped, query is empty
    try: query
    except: query = njs['entities']
    logger.info("%s total: %s skipped, %s updated, %s unchanged" % (len(query), len(skipped), len(updated), len(query) - len(updated)))
    exit(0)
