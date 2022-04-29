#!/bin/bash
# Simple script to start the EA metrics collection python script in the background and keep it running after the user logs out
# Running the script will kill the previous process started by this script and start a new one. 
#
# TO DO:
#  add more more standard service control logic (stop, start, restart, etc.)
#  maybe kill ANY other running job with 'python ea_metrics.py' in the command

# kill any running process
kill `cat ea_metrics.pid`

# Start a new instance
nohup python ./ea_metrics.py > /dev/null &

# Write the PID to file for next time
echo $! > ./ea_metrics.pid
