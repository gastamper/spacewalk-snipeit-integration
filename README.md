# spacewalk-snipeit-integration
This project allows for using Spacewalk as a source for automatically importing and updating assets in Snipe-IT.

# Usage:
 - snipedump: dumps fields from any individual asset in Snipe-IT
 - spacedump: dumps fields from any individual asset in Spacewalk
 - integrator: performs the actual API dump between the two systems

 Edit config.ini to point to the proper Spacewalk & Snipe servers, and include the necessary username/password  
 for Spacewalk, and the API key for Snipe.  Presently, integrator.py will need some custom configuration to make  
 whatever custom fields you may be using match up.
