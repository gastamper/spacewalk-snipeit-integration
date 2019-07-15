# spacewalk-snipeit-integration
This project allows for using Spacewalk as a source for automatically importing and updating assets in Snipe-IT, and vice versa.
Note that it is based on the current working tree and may be inoperable at any given commit.  Regardless, functionality within
your environment *will* require modification of integrator.py.

## Current state:
1. Spacewalk <-> Snipe-IT integration largely works as expected
2. Nutanix API support is preliminary and at present just reports VM count

## Basic usage:
 - snipedump: dumps fields from any assets, models, categories, etc in Snipe-IT (consult built-in help for full list)
 - spacedump: dumps fields from any individual asset in Spacewalk
 - nutanixdump: dumps information from Nutanix about all VMs or a specific VM
 - integrator: performs the actual API dump between the two systems

## How it works
Snipe-IT is authoritative for:
* Assigned user (stored in Spacewalk's "description" details field) and
* Location (stored in Spacewalk's "room" details field)

Spacewalk and Nutanix are authoritative for all applicable hardware and operating system fields:
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

## Configuration
1. Edit config.ini:
    1. Include the proper Spacewalk, Snipe-IT and Nutanix servers.
    2. Define a username and password for Spacewalk and/or Nutanix access.
	3. Set USE_NUTANIX to True if you intend to sync Nutanix VMs.
    4. [Generate and include an API key for Snipe-IT access.](https://snipe-it.readme.io/reference#generating-api-tokens)
2. Edit integrator.py:
   1. The section for determining the matching of Snipe and Spacewalk assets will need to be updated - this is directly below the comment "#CONFIG1".
   2. Determine all asset models and categories by using snipedump to dump one of each type and record the model/category ID number for each.
   3. Update the 'id' and 'name' fields in the section labeled "#CONFIG2" to match the asset models and categories in your environment.
   4. Update the section below the comment "#CONFIG3" to match any custom fields in your environment.
   5. Update the section below the comment "#CONFIG4" to include any fields you would like prepopulated for new Snipe-IT assets.
