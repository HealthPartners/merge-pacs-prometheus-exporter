""" 
Purpose:
  Log in to the EAs with SSH and get free space on each of the unique partions on each of the rcs, elb, and clarc nodes
  Note this will not monitor disk space on dss (image storage) partitions

Prerequisites:
  1) The paramiko package must be installed with 'python -m pip install paramiko'
  2) The prometheus_client package must be installed with 'python -m pip install prometheus_client'
  3) You MUST be able to SSH from the initial server (elb01 or elb02) to ALL other servers in the peer without requiring
      a password. You can do with with shared SSH keys. From both elb servers, do:
          > ssh-keygen -t rsa -b 2048
      then on each elb, execute this command for each server in the peer (including BOTH elb servers, even the one you're on)
          > ssh-copy-id servername

Also, see this page from where I stole the class format used here: https://trstringer.com/quick-and-easy-prometheus-exporter/

NOTE This is written for Python 2.7 which is what's on the EAs.

Created: 3/4/2022
Versions:
 1.0 - 03/04/22 - created by Ben
 2.0 - 03/15/22 - Changed from printing output to using the prometheus_client library to format and host http output
 2.1 - 03/25/22 - Update to change to CONSTANTS for some of the script definitions, added mergeeatestcnt peer definitions, changed polling interval
 """

import logging
from os import name
from paramiko import AuthenticationException, AutoAddPolicy, WarningPolicy, RejectPolicy, BadHostKeyException, ChannelException, SSHException, SSHClient
from prometheus_client import start_http_server, Gauge
import re
from socket import error as socket_error
import sys
import time

"""
General steps:
    Set global definitions for some static information (peers->servers, username, password, log level)
    In main():
        Initialize a new class of AppMetrics (AppMetrics.__init__)
            Declare the metric definitions
            Set http port and refresh times for the looping function
        Start the http mini server process to serve metric results
        Run an infinite loop to refresh the metric data from source every polling interval (AppMetrics.run_metrics_loop)
            Fetch and format metrics data from sources (AppMetrics.fetch)
                Connect to each peer (_connnect_to_ssh)
                Parse output of df commands for each server within each peer
                Assign output to metrics
            [repeat loop]

"""


##
## Definitions
##

# Define each peer and the servers within each peer
peers_and_servers = {
    'mergeeapri' : [
        'elb01',
        'elb02',
        'rcs01',
        'rcs02',
        'clarc01',
        'clarc02',
        'clarc03',
        'clarc04',
        'clarc05',
        'clarc06',
    ],
    'mergeeasec' : [
        'elb01',
        'elb02',
        'rcs01',
        'rcs02',
        'clarc01',
        'clarc02',
        'clarc03',
        'clarc04',
        'clarc05',
        'clarc06',
    ],
    'mergeeatest' : [
        'mergeeatest',  # this is the combined elb/clarc node.. maybe?
        'rcs01',
        'rcs02',
    ],
    'mergeeatestcnt' : [
        'mergeeatestcnt',  # this is the combined elb/clarc node.. maybe?
        'rcs01',
        'rcs02',
    ]
}

# SSH client username and password to connect to each of the EA peers
EA_USERNAME = 'healthpartners'
EA_PASSWORD = 'H3@lthp@rtn3rsP@C5'

# How often the metric data should be refreshed from the application source
POLLING_INTERVAL_SECONDS = 60

# What port this application should host the local http output on (default is 8080)
HOSTING_PORT = 7601

# Define the regex pattern that will match data for the 'df' command output. It should match cases like these:
#   /dev/sda6                          4190208    2114084    2076124  51% /var
#   /dev/mapper/vg00-lv_emageon       35575808    8369020   27206788  24% /opt/emageon
#   192.168.249.49:/vol/backup      2147483648  910542016 1236941632  43% /opt/emageon/backup
df_pattern = re.compile('^(?P<filesystem>[\w\.\:\/]+)\s+(?P<total_KB>\d+)\s+(?P<used_KB>\d+)\s+(?P<available_KB>\d+)\s+(?P<used_perc>\d+)\%\s(?P<mounted_on>[\w\/]+)')

# Set logging parameters
# Change level to print more or fewer debugging messages
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class AppMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Run the collections refresh in a loop (this controls how often data is updated -- it is not updated each time you load the http page)
    * Get the data from the source application
    * 
    """

    def __init__(self, hosting_port=8080, polling_interval_seconds = 20, peer_name=None):
        logging.info('Initializing the metric data class')
        self.hosting_port = hosting_port
        self.polling_interval_seconds = polling_interval_seconds
        self.peer_name = peer_name

        # Define labels to use for each of the metrics (order is important)
        metric_labels = ["peer","server","mount","filesystem"]

        # Define the unique metrics to collect (labels will be added later)
        logging.info('Initializing metric: merge_ea_filesystem_size_used_bytes')
        self.g_used_bytes = Gauge('merge_ea_filesystem_size_used_bytes', 'Number of bytes in use on this filesystem', metric_labels)

        logging.info('Initializing metric: merge_ea_filesystem_size_total_bytes')
        self.g_total_bytes = Gauge('merge_ea_filesystem_size_total_bytes', 'Total capacity of the filesystem', metric_labels)

        #logging.info('Initializing metric: merge_ea_filesystem_size_total_bytes')
        #self.g_available_bytes = Gauge('merge_ea_filesystem_size_available_bytes', 'Total bytes available on this filesystem', metric_labels)

        logging.info('Initializing metric: merge_ea_filesystem_size_used_perc')
        self.g_used_perc = Gauge('merge_ea_filesystem_size_used_perc', 'Percentage of available capacity in use on this filesystem', metric_labels)


    def run_metrics_loop(self):
        """ Loop to update the metrics values at the defined interval"""

        while True:
            if self.peer_name == None:
                self.fetch_through_ea()
            else:
                self.fetch_from_ea(self.peer_name)
            
            time.sleep(self.polling_interval_seconds)


    def fetch_through_ea(self):
        """ 
        Connect to each EA peer and run commands to get the 'df' output from each of the servers within that peer. And
        adds it to a Prometheus metric
        """
        logging.info('Starting to collect metric data from peer(s)')

        for peer in peers_and_servers:
            logging.info('Attempting to collect data from peer %s' % peer)
            servers_in_peer = peers_and_servers[peer]

            # Connect to the peer and returns the Paramiko SSHClient object
            ssh_conn = self._connect_to_ssh(peer, EA_USERNAME, EA_PASSWORD, look_for_keys=False, set_missing_host_key_policy=AutoAddPolicy)

            if ssh_conn:
                for server in servers_in_peer:
                    try:
                        time.sleep(0.1) # I don't know what we need to do this but if there isn't a small delay every other exec_command will fail with an error like: "Secsh channel 3 open FAILED: open failed: Connect failed"
                        df_command = "ssh %s 'df'" % server
                        logging.info('Running command "%s" to collect df data from server %s' % (df_command, server))
                        stdin, stdout, stderr = ssh_conn.exec_command(df_command)
                    except SSHException as sshe:
                        logging.warning('Failed to execute command on %s for peer %s: %s' % (server,peer,sshe))
                    else:
                        # Else the command to get df data from one server ran...
                        if stdout.channel.recv_exit_status() > 0:
                            logging.warning('The command "%s" to get data from %s returned an unexpected status: {stdout.channel.recv_exit_status()}' % (df_command, server))

                        for line in stdout.readlines():
                            # Search for the pattern (defined earlier) to see if this line matches the output we expect
                            match = re.search(df_pattern, line)

                            if match:
                                total_bytes = int(match.group('total_KB')) * 1024
                                mount_point = match.group('mounted_on')
                                used_bytes = int(match.group('used_KB')) * 1024
                                available_bytes = int(match.group('available_KB')) * 1024
                                used_perc = round((used_bytes / total_bytes) * 100, 2)  # Choosing to calculate this here rather than use the pattern match so we get 2 decimals of accuracy rather than the df command's rounding
                                filesystem = match.group('filesystem')

                                # Populate metrics
                                # Bytes in use on the filesystem
                                self.g_used_bytes.labels(peer,server,mount_point,filesystem).set(used_bytes)

                                # Total capacity on the filesystem
                                self.g_total_bytes.labels(peer,server,mount_point,filesystem).set(total_bytes)

                                # Bytes in use on the filesystem
                                #self.g_available_bytes.labels(peer,server,mount_point,filesystem).set(available_bytes)

                                # Bytes in use on the filesystem
                                self.g_used_perc.labels(peer,server,mount_point,filesystem).set(used_perc)

                # Because they are file objects, they need to be closed after reading from all servers before connecting to the next peer
                stdin.close()
                stdout.close()
                stderr.close()

                # Close the connection to the peer
                ssh_conn.close()
                logging.info('Closed connection to peer %s' % peer)

        logging.info('Done fetching metrics for this polling interval. Next fetch in %s seconds' %self.polling_interval_seconds )

    def fetch_from_ea(self, peer):
        """ 
        This assumes the script is running ON one of the EAs (one or both of the elbs), so we can use paramiko to conect and execute commands directly to each server
        """
        logging.info('Starting to collect metric data from server(s) on this peer')
        logging.info('  Local peer name provided: %s' % peer)

        for server in peers_and_servers[peer]:
            logging.info('  Attempting to collect data from server %s' % server)

            # Connect to the server and returns the Paramiko SSHClient object
            ssh_conn = self._connect_to_ssh(server, EA_USERNAME, EA_PASSWORD, look_for_keys=False, set_missing_host_key_policy=AutoAddPolicy)

            if ssh_conn:
                try:
                    #time.sleep(0.1) # I don't know what we need to do this but if there isn't a small delay every other exec_command will fail with an error like: "Secsh channel 3 open FAILED: open failed: Connect failed"
                    df_command = 'df --portability'
                    logging.info('Running command "%s" to collect df data from server %s' % (df_command,server))
                    stdin, stdout, stderr = ssh_conn.exec_command(df_command)
                except SSHException as sshe:
                    logging.warning('  Failed to execute command on %s for peer %s: %s' % (server,peer,sshe))
                else:
                    # Else the command to get df data from one server ran...
                    if stdout.channel.recv_exit_status() > 0:
                        logging.warning('  The command "%s" to get data from %s returned an unexpected status: {stdout.channel.recv_exit_status()}' % (df_command,server))

                    for line in stdout.readlines():
                        # Search for the pattern (defined earlier) to see if this line matches the output we expect
                        match = re.search(df_pattern, line)

                        if match:
                            total_bytes = int(match.group('total_KB')) * 1024
                            mount_point = match.group('mounted_on')
                            used_bytes = int(match.group('used_KB')) * 1024
                            available_bytes = int(match.group('available_KB')) * 1024
                            used_perc = round((used_bytes / total_bytes) * 100, 2)  # Choosing to calculate this here rather than use the pattern match so we get 2 decimals of accuracy rather than the df command's rounding
                            filesystem = match.group('filesystem')

                            # Populate metrics
                            # Bytes in use on the filesystem
                            self.g_used_bytes.labels(peer,server,mount_point,filesystem).set(used_bytes)

                            # Total capacity on the filesystem
                            self.g_total_bytes.labels(peer,server,mount_point,filesystem).set(total_bytes)

                            # Bytes in use on the filesystem
                            #self.g_available_bytes.labels(peer,server,mount_point,filesystem).set(available_bytes)

                            # Bytes in use on the filesystem
                            self.g_used_perc.labels(peer,server,mount_point,filesystem).set(used_perc)

                # Because they are file objects, they need to be closed after reading from all servers before connecting to the next peer
                stdin.close()
                stdout.close()
                stderr.close()

                # Close the connection to the peer
                ssh_conn.close()
                logging.info('  Closed connection to %s' % server)

            else:
                logging.warning('  Failed to collect data from %s' % server)

        logging.info('Done fetching metrics for this polling interval. Next fetch in %s seconds' % self.polling_interval_seconds)


    def _connect_to_ssh(self, target_host, username, password, look_for_keys=False, set_missing_host_key_policy=WarningPolicy):

        # Create new paramiko SSH client object
        ssh_conn = SSHClient()

        # Set policy on what to do if the host key is not already in the local key stores. Default is to warn but accept it. You may want to use AutoAddPolicy.
        # See Paramiko documentation for details
        if set_missing_host_key_policy:
            ssh_conn.set_missing_host_key_policy(set_missing_host_key_policy)
        
        try:
            logging.info('Attempting to connect to %s as user %s.' % (target_host,username))
            ssh_conn.connect(target_host, username=username, password=password, look_for_keys=look_for_keys)
        except AuthenticationException as ae:
            logging.error('Could not connect to %s. Could not authenticate with %s and %s: %s' % (target_host,EA_USERNAME,EA_PASSWORD,ae))
        except SSHException as sshe:
            logging.error('SSHException connecting to %s: %s' % (target_host,sshe))
        except socket_error as se:
            logging.error('Socket error when connecting to %s: %s (error number: %s)' % (target_host,se,se.errno))
        else:
            # If we can connect to this peer...
            return ssh_conn

def main():
    """Main entry point"""

    # If an argument is provided it should be the name of the current peer (i.e. mergeeapri or mergeeatest). That will
    # indicate we should be running in "local" mode and are being run directly on one of the EAs
    try:
        arg1 = sys.argv[1]
    except:
        logging.warning('No argument provided!')
        print('No argument provided. Usage is: ')
        print('   > %s <node hostname>|remote' % sys.argv[0])
        print('')
        print('Use "remote" when you are running this script from a location other than one of the EAs.')
        print('Otherwise the argument should be the name of the EA peer on which this script is running which is one of:')
        print('   %s' % ", ".join(peers_and_servers.keys()) )
        print('')
        exit()

    if(arg1 == "remote"):
        logging.info('Running in "remote" mode from a location other than one of the EAs')
        name_of_peer = None
    else:
        name_of_peer = sys.argv[1]
        logging.info('Running metrics collection in "local" mode assuming this is running directly on: %s' % name_of_peer)
        if name_of_peer not in peers_and_servers.keys():
            logging.error('The hostname %s is not defined in this script so results will probably not be what you expect!' % name_of_peer)

    # Initialize a new class to set up all of the class definitions, define the metrics, etc.
    app_metrics = AppMetrics(hosting_port=HOSTING_PORT, polling_interval_seconds=POLLING_INTERVAL_SECONDS, peer_name=name_of_peer)
    
    # Start up the http mini-server
    logging.info('Starting http server on port %s' % HOSTING_PORT)
    start_http_server(HOSTING_PORT)

    # Start the infinite loop that will refresh the metrics at every polling interval
    app_metrics.run_metrics_loop()

    logging.warning('Somehow we have existed the metrics collection loop!')


if __name__ == "__main__":
    main()