# spacewalk-snipeit-integration
This project allows for using Spacewalk and Nutanix as sources for automatically importing and updating assets in Snipe-IT, and vice versa.
Note that it is based on the current working tree and may be inoperable at any given commit.  Regardless, functionality within
your environment *will* require modification of integrator.py to support any necessary custom fields you may use (CPU/RAM/network information, etc).

## Current state:
- [x] Basic Spacewalk API integration done (built-in Snipe-IT fields supported)
- [x] Custom fields in Snipe-IT supported for Spacewalk data
- [x] Manufacturers automatically added to Snipe-IT based on Spacewalk chassis data
- [x] Models automatically added to Snipe-IT based on Spacewalk chassis data
- [x] Basic Nutanix API integration done (built-in Snipe-IT fields supported)
- [x] Custom fields in Snipe-IT supported for Nutanix data
- [x] Option to skip either Nutanix or Spacewalk integration via config file or command line

## Basic usage:
 - snipedump: dumps fields from any assets, models, categories, etc in Snipe-IT (consult built-in help for full list)
 - spacedump: dumps fields from any individual asset in Spacewalk
 - nutanixdump: dumps information from Nutanix about all VMs or a specific VM
 - integrator: performs the actual API updates between Snipe-IT and Spacewalk/Nutanix systems
  
Consult integrator.py's builtin --help for available command-line options
  
## How it works
Snipe-IT is authoritative for:
* Assigned user (stored in Spacewalk's "description" details field) and
* Location (stored in Spacewalk's "room" details field)

Spacewalk and Nutanix are authoritative for all applicable hardware and operating system fields:
* Manufacturer
* Asset model
* Asset type (derived from hostname in the example scenario)
* Asset tag (derived from hostname for laptops & desktops in example scenario)
* Serial number (derived from chassis field via DMI in example scenario)
* Item name  
As well as the custom fields:
* IP address
* Operating system and version
* Total RAM
* Total CPU
* Total cores
* UUID (for tracking Nutanix VMs)

## Configuration
1. Edit config.ini:
    1. Include the proper Spacewalk, Snipe-IT and Nutanix servers where applicable.
    2. Define a username and password for Spacewalk and/or Nutanix access.
    3. Set USE_NUTANIX to True if you intend to sync Nutanix VMs.
	4. Use snipedump.py to determine your default fieldset and category ids, and the names of any custom fields you are using.
    4. [Generate and include an API key for Snipe-IT access.](https://snipe-it.readme.io/reference#generating-api-tokens)
2. Edit integrator.py:
   1. The section for determining the matching of Snipe and Spacewalk assets will need to be updated - this is directly below the comment "#CONFIG1".
   2. Determine all asset models and categories by using snipedump to dump one of each type and record the model/category ID number for each.
   3. Update the 'id' and 'name' fields in the section labeled "#CONFIG2" to match the asset models and categories in your environment.
   4. If necessary, update the section below the comment "#CONFIG3" to match any custom fields in your environment.
   5. Update the section below the comment "#CONFIG4" to include any fields you would like prepopulated for new Snipe-IT assets.

## API rate limit
See [this portion of the API reference](https://snipe-it.readme.io/reference#api-throttling) for modifying the API rate limit on Snipe-IT.
