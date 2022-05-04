#!/bin/bash
# Simple script to start the EA metrics collection python script in the background and keep it running after the user logs out
# Running the script will kill the previous process started by this script and start a new one. 
#
# TO DO:
#  add more more standard service control logic (stop, start, restart, etc.)
#  maybe kill ANY other running job with 'python ea_metrics.py' in the command

# kill any running process
kill `cat ea_metrics.pid`

# Check if usernames and passwords are already set in environment variable and prompt if not
if [ -z ${SSH_USERNAME+x} ]; then 
    read -p "Type in the username to use for connecting via ssh to each server: " MY_SSHUSERNAME
    export SSH_USERNAME="$MY_SSHUSERNAME"
else 
    echo "Using SSH_USERNAME from environment variables"
fi

if [ -z ${SSH_PASSWORD+x} ]; then 
    read -p "Type in the password to use for connecting via ssh to each server: " MY_SSHPASSWORD
    export SSH_PASSWORD="$MY_SSHPASSWORD"
else 
    echo "Using SSH_PASSWORD from environment variables"
fi

if [ -z ${EAWEB_USERNAME+x} ]; then 
    read -p "Type in the username to use for connecting via ssh to each server: " MY_EAWEBUSERNAME
    export EAWEB_USERNAME="$MY_EAWEBUSERNAME"
else 
    echo "Using EAWEB_USERNAME from environment variables"
fi

if [ -z ${EAWEB_PASSWORD+x} ]; then 
    read -p "Type in the password to use for connecting via ssh to each server: " MY_EAWEBPASSWORD
    export EAWEB_PASSWORD="$MY_EAWEBPASSWORD"
else 
    echo "Using EAWEB_PASSWORD from environment variables"
fi

# Start a new instance
nohup python ./ea_metrics.py > /dev/null &

# Write the PID to file for next time
echo $! > ./ea_metrics.pid
