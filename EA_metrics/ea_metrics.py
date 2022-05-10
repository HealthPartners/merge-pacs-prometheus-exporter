""" 
Purpose:
    This assumes you are running the script on one of the EAs. It will collect a few different types of metric data and host them on a local
    http server using the prometheus_client package.

Prerequisites:
  0) Test if pip is installed with 'python -m pip --version'. If not, install pip:
     > curl -sSL https://bootstrap.pypa.io/pip/2.7/get-pip.py --insecure -o get-pip.py
     > python get-pip.py --trusted-host pypi.org --trusted-host files.pythonhosted.org
  1) The python packages paramiko, prometheus_client, and requests must be installed. Assuming you're not running as root, they can be installed for
     the local user. Run the following to installed (and ignore our web filter's self-signed certificate):
        python -m pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --user paramiko prometheus_client requests
  2) You MUST be able to SSH from the initial server (elb01 or elb02) to ALL other servers in the peer without requiring
      a password. You can do with with shared SSH keys. From both elb servers, do:
          > ssh-keygen -t rsa -b 2048
      then on each elb, execute this command for each server in the peer (including BOTH elb servers, even the one you're on)
          > ssh-copy-id servername

Deployment:
* Copy all files to ~/hpmetrics and update any that are already there with the new versions
* Give permissions to allow run_metrics.sh to be executed if it is newly created:
        chmod u+x ~/hpmetrics/run_metrics.sh

Running the metrics collection:
* ~/hpmetrics/run_metrics.sh

Also, see this page from where I stole the class format used here: https://trstringer.com/quick-and-easy-prometheus-exporter/

NOTE This is written for Python 2.7 which is what's on the EAs.

Created: 4/24/2022
Versions:
 1.0 - 4/24/22 - created by Ben
 1.1 - 5/2/22  - Revision to exclude tmpfs and devtmpfs filesystems from disk utilization metrics; fix disk utilization pattern match
                 to capture /dev/mapper... volumes, too
 1.2 - 5/4/22  - Add collection of SWE metrics from web admin here (previously it was on the cdsmi server's Merge PACS script)
 1.3 - 5/4/22  - Add a .clear() to the collection process for SWE. When there is no data for a combination of labels the gauge will
                 continue to report the most recent value instead of 0 or null. This resets it each time which is necessary since the
                 jquery output won't have any at all when a particular component/task combo has no messages in queue.
 """

from contextlib import closing
import logging
import os
from paramiko import AuthenticationException, AutoAddPolicy, WarningPolicy, BadHostKeyException, ChannelException, SSHException, SSHClient
from prometheus_client import start_http_server, Gauge, Info
import re
import requests
import requests.exceptions
import socket
import sys
import time

##
## Definitions
##

# Current software version
CURRENT_VERSION = 1.3

# How often the metric data should be refreshed from the application source
POLLING_INTERVAL_SECONDS = 60

# What port this application should host the local http output on (default is 8080)
HOSTING_PORT = 7601

# SSH client username and password to connect to each of the EA peers
# You can define it here if you must. Better still, you can define it in environmental variables before running the script. But the
# best idea is just to copy your shared SSH key to every target do you don't need to use a username and password for that part. But
# you will still need it defined if you're going to log in to the EA web admin to scrape the SWE sizes. getenv returns a "None" value
# the the environment variable is not present.
SSH_USERNAME = os.getenv('SSH_USERNAME')
SSH_PASSWORD = os.getenv('SSH_PASSWORD')
EAWEB_USERNAME = os.getenv('EAWEB_USERNAME')
EAWEB_PASSWORD = os.getenv('EAWEB_PASSWORD')

if EAWEB_USERNAME is None or EAWEB_PASSWORD is None:
    logging.error('The username and password to use to authenticate to EA Web are not defined correctly! This will probably prevent the SWE metrics from being collected.')

# How long we should wait for an HTTP connection attempt to be successful before failing, in seconds
DEFAULT_HTTP_TIMEOUT = 2.0

# Set logging parameters
# Change level to print more or fewer debugging messages
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ExporterSelfMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, peer_name=None, metric_prefix='merge_ea_unk', metric_service_description="service name"):
        logging.info('Initializing the %s metric data class' % metric_service_description)

        # The name of the current peer (the VIP hostname)
        self.peer_name = peer_name
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # The description of the server
        self.service_description = metric_service_description
        
        # Define the unique metrics to collect (labels will be added later)
        self.i_exporter_version = Info(self.prefix, 'The version of this prometheus exporter script', ['peer', 'version'])

    def fetch(self):
        """ 
        Populate the metric with the current version number
        """
        logging.info('Gathering metric data for %s' % self.service_description)

        # Create info metric with version number of this script
        self.i_exporter_version.labels(peer=self.peer_name, version=CURRENT_VERSION)

        logging.info('Done fetching metrics for this polling interval for %s' % self.service_description)

class DiskUtilizationMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from each server in the peer by connecting via ssh into each one
    * Helper function for ssh connections
    """

    def __init__(self, peer_name=None, metric_prefix='merge_ea_unk', metric_service_description="service description", server_list=[]):
        self.service_description = metric_service_description
        logging.info('Initializing the %s metric data class' % self.service_description)

        self.peer_name = peer_name
        self.server_list = server_list


        # Define the regex pattern that will match data for the 'df' command output. It should match cases like these:
        #   /dev/sda6                          4190208    2114084    2076124  51% /var
        #   /dev/mapper/vg00-lv_emageon       35575808    8369020   27206788  24% /opt/emageon
        #   192.168.249.49:/vol/backup      2147483648  910542016 1236941632  43% /opt/emageon/backup
        self.df_pattern = re.compile('^(?P<filesystem>[\w\d\-\/]+)\s+(?P<total_KB>\d+)\s+(?P<used_KB>\d+)\s+(?P<available_KB>\d+)\s+(?P<used_perc>\d+)\%\s(?P<mounted_on>[\w\/]+)')

        # Define labels to use for each of the metrics (order is important)
        metric_labels = ["peer","server","mount","filesystem"]

        # Define the unique metrics to collect (labels will be added later)
        logging.info('Initializing metric: merge_ea_filesystem_size_used_bytes')
        self.g_used_bytes = Gauge('%s_size_used_bytes' % metric_prefix, 'Number of bytes in use on this filesystem', metric_labels)

        logging.info('Initializing metric: merge_ea_filesystem_size_total_bytes')
        self.g_total_bytes = Gauge('%s_size_total_bytes' % metric_prefix, 'Total capacity of the filesystem', metric_labels)

        #logging.info('Initializing metric: merge_ea_filesystem_size_total_bytes')
        #self.g_available_bytes = Gauge('merge_ea_filesystem_size_available_bytes', 'Total bytes available on this filesystem', metric_labels)

    def fetch(self):
        """ 
        Use paramiko to conect to each clarc server via ssh and execute df commands directly to each server
        """
        logging.info('Starting to collect %s metric data from server(s) on this peer' % self.service_description)
        logging.info('  Local peer name provided: %s' % self.peer_name)

        for server in self.server_list:
            logging.info('  Attempting to collect data from server %s' % server)

            # Connect to the server and returns the Paramiko SSHClient object
            ssh_conn = _connect_to_ssh(target_host=server, username=SSH_USERNAME, password=SSH_PASSWORD)    # Use environment variables for username and password, if present

            if ssh_conn:
                try:
                    #time.sleep(0.1) # I don't know what we need to do this but if there isn't a small delay every other exec_command will fail with an error like: "Secsh channel 3 open FAILED: open failed: Connect failed"
                    df_command = 'df --portability --local --exclude-type=tmpfs --exclude-type=devtmpfs'
                    logging.info('  Running command "%s" to collect df data from server %s' % (df_command,server))
                    stdin, stdout, stderr = ssh_conn.exec_command(df_command)
                except SSHException as sshe:
                    logging.warning('  Failed to execute command on %s for peer %s: %s' % (server,self.peer_name,sshe))
                    logging.raiseExceptions
                else:
                    # Else the command to get df data from one server ran...
                    if stdout.channel.recv_exit_status() > 0:
                        logging.warning('  The command "%s" to get data from %s returned an unexpected status: {stdout.channel.recv_exit_status()}' % (df_command,server))

                    for line in stdout.readlines():
                        # Search for the pattern (defined earlier) to see if this line matches the output we expect
                        match = re.search(self.df_pattern, line)

                        if match:
                            total_bytes = float(match.group('total_KB')) * 1024
                            mount_point = match.group('mounted_on')
                            used_bytes = float(match.group('used_KB')) * 1024
                            available_bytes = float(match.group('available_KB')) * 1024
                            filesystem = match.group('filesystem')

                            # Populate metrics
                            # Bytes in use on the filesystem
                            ["peer","server","mount","filesystem"]
                            self.g_used_bytes.labels(peer=self.peer_name, server=server, mount=mount_point, filesystem=filesystem).set(used_bytes)

                            # Total capacity on the filesystem
                            self.g_total_bytes.labels(peer=self.peer_name, server=server, mount=mount_point, filesystem=filesystem).set(total_bytes)

                            # Bytes in use on the filesystem
                            #self.g_available_bytes.labels(peer,server,mount_point,filesystem).set(available_bytes)

                # Because they are file objects, they need to be closed after reading from all servers before connecting to the next peer
                stdin.close()
                stdout.close()
                stderr.close()

                # Close the connection to the peer
                ssh_conn.close()
                logging.info('  Closed connection to %s' % server)

            else:
                logging.warning('  Failed to collect data from %s' % server)

        logging.info('  Done fetching %s metrics for this polling interval' % self.service_description)

class ClarcAvailabilityMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from each server in the peer by connecting via ssh into each one
    * Helper function for ssh connections
    """

    def __init__(self, peer_name=None, metric_prefix='merge_ea_unk', metric_service_description="service description", server_list=[]):
        self.service_description = metric_service_description
        logging.info('Initializing the %s metric data class' % self.service_description)

        self.peer_name = peer_name

        # Get only the clarc servers out of this list of all servers in this peer
        self.clarc_server_list = [s for s in server_list if "clarc" in s]
        if not self.clarc_server_list:
            self.clarc_server_list = [peer_name]  # this is a standalone system with no separate clarc, so use the current host

        # Define labels to use for each of the metrics (order is important)
        metric_labels = ["peer","server"]

        # Define the unique metrics to collect (labels will be added later)
        logging.info('Initializing metric: %s_status' % metric_prefix)
        self.g_status = Gauge('%s_status' % metric_prefix, 'Status of clarc server as determined by whether or not it is listening on port 12000', metric_labels)

    def  _check_socket_listening(self, host, port):
        """ Return True if we the target host and port is listenting, False if not."""
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(2.0)    # Set a 2 second timeout
            if sock.connect_ex((host, port)) == 0:
                # port is open and listening
                return True
            else:
                # port is not open and listening
                return False

    def fetch(self):
        """ 
        Fetch the clarc status of each clarc server in this peer by checking to see if it port 12000 is open to connections.
        If we're running in SSA (standalone) mode, there is only one server so check that port 12000 is open on the current host.
        """
        logging.info('Starting to collect %s metric data from server(s) on this peer' % self.service_description)

        for clarc_server in self.clarc_server_list:
            logging.info('  Attempting to check status of server %s' % clarc_server)
            try:
                if self._check_socket_listening(clarc_server, 12000):
                    # server is listening on port 12000
                    self.g_status.labels(self.peer_name, clarc_server).set(1.0)
                else:
                    # port 12000 is not open
                    self.g_status.labels(self.peer_name, clarc_server).set(0.0)
            except:
                logging.warning('  Failed to collect data from %s' % clarc_server)
                logging.raiseExceptions

        logging.info('  Done fetching %s metrics for this polling interval' % self.service_description)

class MulticasterMetrics:
    """
    Functions to monitor the size of each of the peer's multicaster queues:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, peer_name=None, metric_prefix='merge_ea_unk', metric_service_description="service name", server_list=[]):
        logging.info('Initializing the %s metric data class' % metric_service_description)

        # The name of the current peer (the VIP hostname)
        self.peer_name = peer_name
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # The description of the server
        self.service_description = metric_service_description

        # List of all servers in this peer
        self.server_list = server_list

        # Define the unique metrics to collect (labels will be added later)
        self.g_queue_size = Gauge('%s_queue_size' % self.prefix, 'The number of messages waiting to be processed by each multicaster queue', ['peer', 'queue'])

    def fetch(self):
        """ 
        Collect the size of the multicaster queues (excluding error queues) for the peer. Technically non-cluster nodes only have
        one server doing everything so you can execute the OS command locally. But for clustered systems you need to SSH to one
        of the rcs or elb servers first. To simplify, just SSH to (arbitrarily) rcs02 every time because this will actually work
        even on a standalone node, and executing shell commands in Python 2.7 is slightly non-trivial.
        """
        logging.info('Starting to collect %s metric data from server(s) on this peer' % self.service_description)

        # need to:
        # If a cluster, ssh to rcs01/02
        # cd /opt/emageon/var/multicaster/storage/
        # Get directories, excluding *_errors
        # Recursive count of files in each dir
        # split server, port from dir name
        command = 'for i in `ls /opt/emageon/var/multicaster/storage --hide="*error*"`; do echo "$i `find /opt/emageon/var/multicaster/storage/$i -type f | wc -l`"; done'

        server = 'rcs02'
        ssh_conn = _connect_to_ssh(target_host=server, username=os.getenv('EA_USERNAME'), password=os.getenv('EA_PASSWORD'))    # Use environment variables for username and password, if present

        if ssh_conn:
            try:
                logging.info('  Running command "%s" to collect df data from server %s' % (command, server))
                stdin, stdout, stderr = ssh_conn.exec_command(command)
            except SSHException as sshe:
                logging.warning('  Failed to execute command on %s for peer %s: %s' % (server, self.peer_name, sshe))
            else:
                # Else the command to get df data from one server ran...
                if stdout.channel.recv_exit_status() > 0:
                    logging.warning('  The command "%s" to get data from %s returned an unexpected status: {stdout.channel.recv_exit_status()}' % (command, server))

                for line in stdout.readlines():
                    # Expected command output:
                    # clarc01_12999 0
                    # clarc02_12250 10
                    # ...
                    # inbound_queue 0
                    # peerarchive_12800 0
                    # vas_5001 0

                    try:
                        queue_name, size = line.split()
                        # Populate metrics
                        self.g_queue_size.labels(peer=self.peer_name, queue=queue_name).set(size)
                    except:
                        logging.info('  The command output line could not be parsed for queue name and size: %s' % line)
                        logging.raiseExceptions

            # Because they are file objects, they need to be closed after reading from all servers before connecting to the next peer
            stdin.close()
            stdout.close()
            stderr.close()

            # Close the connection to the peer
            ssh_conn.close()
            logging.info('  Closed connection to %s' % server)

        logging.info('Done fetching metrics for this polling interval for %s' % self.service_description)

class ScheduledWorkEngineMetrics:
    """
    Functions to monitor the size of each of the peer's scheduled work engine queues:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, peer_name=None, metric_prefix='merge_ea_unk', metric_service_description="service name", server_list=[], peer_domain='healthpartners.com'):
        logging.info('Initializing the {} metric data class'.format(metric_service_description))

        # The name of the current peer (the VIP hostname)
        self.peer_name = peer_name
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # The description of the server
        self.service_description = metric_service_description

        # List of all servers in this peer
        self.server_list = server_list

        # Domain for this peer (the VIP domain name). Some peers don't recognize the "peer name" as a valid network address without the FQDN
        self.peer_domain = peer_domain

        self.peer_fqdn = '{0}.{1}'.format(peer_name, peer_domain)

        # Define the unique metrics to collect (labels will be added later)
        self.g_queue_size = Gauge('{}_queue_size'.format(self.prefix),
            'The number of notifications waiting to be sent to Merge PACS by the scheduled work engine, grouped by component name and task type',
            ['peer', 'component_name', 'task_name', 'status']
        )

    def fetch(self):
        """ 
        Collect the size of the SWE queues for the peer. The only good way to do this (since we can't query the DB directly) is 
        scrape the webadmin page and use its jquery response. This means we have to be able to log in to the webadmin page using
        a valid username and password.
        """
        logging.info('Starting to collect {} metric data from server(s) on this peer'.format(self.service_description))

        sess = requests.Session()

        login_url = 'https://{}/eaweb/login'.format(self.peer_fqdn)

        try:
            logging.info('   Getting EA web admin login page')
            r = sess.get(login_url, verify=False, timeout=DEFAULT_HTTP_TIMEOUT)
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            logging.error('HTTP status error when attempting to open the EA web admin login page! ({})'.format(login_url))
            logging.raiseExceptions
        except requests.exceptions.Timeout as err:
            logging.error('HTTP timeout when attempting to open the EA web admin login page! ({})'.format(login_url))
            logging.raiseExceptions
            # Maybe set up for a retry, or continue in a retry loop
        except requests.exceptions.RequestException as e:
            logging.error('HTTP error when attempting to open the EA web admin login page ({0}): {1}'.format(login_url, e))
            logging.raiseExceptions

        # Parse content and get the hidden _csrf token from the login page raw html text
        pattern = re.compile(r'<input type="hidden" name="_csrf" value="(?P<csrf>[\d\w\-]+)" />')
        match = re.search(pattern, r.text)
        csrf_token = match.group('csrf')

        # Contruct login form submission payload
        payload = {
            'username' : EAWEB_USERNAME,
            'password': EAWEB_PASSWORD,
            'ldapDomain': '1',       # Assume that 'healthpartners.int' is the only option other than Local
            '_csrf': csrf_token
        }

        try:
            # Do not verify certificates because the EA's are self-signed
            logging.info('   Authenticating to EA web admin')
            post = sess.post(login_url, data=payload, verify=False, timeout=DEFAULT_HTTP_TIMEOUT)
            post.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logging.error('HTTP status error when attempting to log in to EA web admin ({0}): {1}'.format(login_url, e.response.status))
            logging.raiseExceptions
        except requests.exceptions.RequestException as e:
            logging.error('HTTP error when attempting to log in to EA web admin ({0}): {1}'.format(login_url, e))
            logging.raiseExceptions


        # Execute this call first to prepare results even though we don't use the response directly
        execute_jquery_url = 'https://{0}/eaweb/monitoring/scheduledwork/getsummaryresult?componentName=&taskName=&status=&_filterByGroupFlag=on&_actionGroupsFlag=on&groupIdentifier=&selectedAction=&singleCheckedItem=&nextAttemptDate=03%2F23%2F2022&nextAttemptTime=13%3A50&_csrf={1}' \
            .format(self.peer_fqdn, csrf_token)
        logging.info('   Starting query of SWE status data')
        try:            
            jquery_response = sess.get(execute_jquery_url, verify=False, timeout=DEFAULT_HTTP_TIMEOUT)
            jquery_response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logging.error('HTTP status error when attempting to prepare jquery: {}'.format(e.response.status))
            logging.raiseExceptions
        except requests.exceptions.RequestException as e:
            logging.error('HTTP error when attempting to prepare jquery: {}'.format(e))
            logging.raiseExceptions

        # Note sure of the significance of the "draw=" argument to the function here. The page makes two calls with the value set to both 1 and 2. But setting it to 0 or ommitting it also seems to generate the same results.
        current_unix_timestamp = int(time.time()*1000)
        get_jquery_result_url = 'https://{0}/eaweb/monitoring/scheduledwork/getsummarypaginationresults?draw=0&columns%5B0%5D.data=Select&columns%5B0%5D.name=&columns%5B0%5D.searchable=true&columns%5B0%5D.orderable=false&columns%5B0%5D.search.value=&columns%5B0%5D.search.regex=false&columns%5B1%5D.data=componentName&columns%5B1%5D.name=&columns%5B1%5D.searchable=true&columns%5B1%5D.orderable=true&columns%5B1%5D.search.value=&columns%5B1%5D.search.regex=false&columns%5B2%5D.data=taskName&columns%5B2%5D.name=&columns%5B2%5D.searchable=true&columns%5B2%5D.orderable=true&columns%5B2%5D.search.value=&columns%5B2%5D.search.regex=false&columns%5B3%5D.data=groupIdentifier&columns%5B3%5D.name=&columns%5B3%5D.searchable=true&columns%5B3%5D.orderable=true&columns%5B3%5D.search.value=&columns%5B3%5D.search.regex=false&columns%5B4%5D.data=status&columns%5B4%5D.name=&columns%5B4%5D.searchable=true&columns%5B4%5D.orderable=true&columns%5B4%5D.search.value=&columns%5B4%5D.search.regex=false&columns%5B5%5D.data=count&columns%5B5%5D.name=&columns%5B5%5D.searchable=true&columns%5B5%5D.orderable=false&columns%5B5%5D.search.value=&columns%5B5%5D.search.regex=false&order%5B0%5D.column=1&order%5B0%5D.dir=asc&start=0&length=50&search.value=&search.regex=false&_={1}' \
            .format(self.peer_fqdn, current_unix_timestamp)
        try:
            get_jquery_result_response = sess.get(get_jquery_result_url, verify=False, timeout=DEFAULT_HTTP_TIMEOUT)
            get_jquery_result_response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logging.error('HTTP status error when attempting to get jquery response: {}'.format(e.response.status))
            logging.raiseExceptions
        except requests.exceptions.RequestException as e:
            logging.error('HTTP error when attempting to get jquery response:{}'.format(e))
            logging.raiseExceptions

        jsonResponse = get_jquery_result_response.json()

        # Clear out the gague metric's previous labels and values. Otherwise if there's no data in this scrape for a particular label combination
        # gague will just report out the most recent value. That's not exactly what we want.
        self.g_queue_size.clear()

        for data_item in jsonResponse['data']:
            self.g_queue_size.labels(peer=self.peer_name, component_name=data_item['componentName'], task_name=data_item["taskName"], status=data_item["status"]).set(data_item["count"])

        logging.info('Done fetching metrics for this polling interval for %s' % self.service_description)


def _initialize_metric_classes(peer_name, peer_domain, server_list):
    """
    Initialize each of the promtheus_client classes for each of the metrics we're going to collect. 
    Arguments: 
        * The name of the peer (the VIP hostname) we're collecting data for
        * The domain of the peer (the VIP domain) we're collecting data for
        * A list of all servers (elb, rcs, clarc) in this peer
    Returns: A list of class objects initialized. Use these objects to call the fetch() method for each one to 
        populate the registry with metric values.
    """

    metric_class_objects = []

    #exporter_self_metrics = ExporterSelfMetrics(peer_name=peer_name, metric_prefix='merge_ea_exporter', metric_service_description="exporter")
    metric_class_objects.append(
        ExporterSelfMetrics(peer_name=peer_name, metric_prefix='merge_ea_exporter', metric_service_description="exporter")
    )
    
    #disk_utilization_metrics = DiskUtilizationMetrics(peer_name=peer_name, metric_prefix='merge_ea_filesystem', metric_service_description="disk utilization", server_list=server_list)
    metric_class_objects.append(
        DiskUtilizationMetrics(peer_name=peer_name, metric_prefix='merge_ea_filesystem', metric_service_description="disk utilization", server_list=server_list)
    )

    #clarc_availability_metrics = ClarcAvailabilityMetrics(peer_name=peer_name, metric_prefix='merge_ea_clarc', metric_service_description="clarc availability", server_list=server_list)
    metric_class_objects.append(
        ClarcAvailabilityMetrics(peer_name=peer_name, metric_prefix='merge_ea_clarc', metric_service_description="clarc availability", server_list=server_list)
    )

    metric_class_objects.append(
        MulticasterMetrics(peer_name=peer_name, metric_prefix='merge_ea_multicaster', metric_service_description='multicaster', server_list=server_list)
    )

    metric_class_objects.append(
        ScheduledWorkEngineMetrics(peer_name=peer_name, metric_prefix='merge_ea_scheduledworkengine', metric_service_description='scheduled work engine', server_list=server_list, peer_domain=peer_domain)
    )
    
    return metric_class_objects

def _connect_to_ssh(target_host, username, password, look_for_keys=True, set_missing_host_key_policy=WarningPolicy):

    # Create new paramiko SSH client object and load known host keys
    ssh_conn = SSHClient()
    ssh_conn.load_system_host_keys()

    # Set policy on what to do if the host key is not already in the local key stores. Default is to warn but accept it. You may want to use AutoAddPolicy.
    # See Paramiko documentation for details
    if set_missing_host_key_policy:
        ssh_conn.set_missing_host_key_policy(set_missing_host_key_policy)
    
    try:
        logging.info('  Attempting to connect to %s as user %s.' % (target_host,username))
        ssh_conn.connect(target_host, username=username, password=password, look_for_keys=look_for_keys)
    except AuthenticationException as ae:
        logging.error('  Could not connect to %s. Could not authenticate with %s and %s: %s' % (target_host,username,password,ae))
    except SSHException as sshe:
        logging.error('  SSHException connecting to %s: %s' % (target_host,sshe))
    except socket.error as se:
        logging.error('  Socket error when connecting to %s: %s (error number: %s)' % (target_host,se,se.errno))
    else:
        # If we can connect to this peer...
        return ssh_conn

def _get_conf_data_as_dict(path = '/etc/emageon.conf'):
    """ Gets configuration data from an env-style file and returns variables and values in a dictionary format.
        Intended generally to be used in parsing something like /etc/emageon.conf.
    """
    logging.info('Attempting to read configuration file: %s' % path)
    vars_dict = {}
    with open(path, 'r') as f:
        for line in f.readlines():
            if line.startswith('#') or '=' not in line:
                continue
            else:
                key, value = line.strip().split('=', 1)
                vars_dict[key] = value.replace('"','') # Save to a dict, removing the double quotes if any
    return vars_dict

def _get_netinfo(configuration_vars):
    """ Returns:
            * This peer's VIP name
            * domain name
            * VIP IP address
            * VIP netmask bits
            * Gateway IP address
            provided a dictionary of configuration variables from the emageon.conf file
    """
    try:
        pattern = re.compile(r'(?P<vip_hostname>[^\.]+)(\.)?(?P<vip_domainname>[^,]*)\,(?P<vip_ip>[\d\.]*)\/(?P<vip_netmask_bits>\d+)\,(?P<vip_gateway>[\d\.]*)')
        match = re.search(pattern, configuration_vars['FE_NETINFO'])
        return [
            match.group('vip_hostname').lower(),
            match.group('vip_domainname').lower(),
            match.group('vip_ip'),
            match.group('vip_netmask_bits'),
            match.group('vip_gateway'),

        ]
    except:
        logging.warning('Could not correctly parse FE_NETINFO configuration values')
        logging.raiseExceptions

def _get_clarc_servers(configuration_vars):
    """ Returns a list of clarc server names provided a dictionary of configuration variables from the emageon.conf
        file or returns an empty list if this peer does not have dedicated clarc servers (i.e. is not clustered)
    """
    clarcs_list = []
    try:
        for num in range(1, int(configuration_vars['NUM_CLARCS']) + 1):
            clarcs_list.append('clarc%02d' % int(num))
        return clarcs_list
    except:
        logging.warning('Could not correctly generate a list of clarc servers for configuration value of NUM_CLARCS')

def _get_servers_in_peer(configuration_vars):
    """Given the configuration variables from emageon.conf, return a list of all server names for this peer"""
    if configuration_vars['SYSTEM_ARCH'] == 'SSA':
        # This is a standalone system, everything is running on one VM
        vip_hostname, vip_domainname, vip_ip, vip_netmask_bits, vip_gateway = _get_netinfo(configuration_vars)
        all_servers_list = [vip_hostname]
        return all_servers_list
    elif configuration_vars['SYSTEM_ARCH'] == 'CLUSTER':
        clarcs_list = _get_clarc_servers(configuration_vars)
        all_servers_list = ['elb01', 'elb02', 'rcs01', 'rcs02']
        all_servers_list.extend(clarcs_list)
        return all_servers_list
    else:
        logging.warning('Failed to match the SYSTEM_ARCH configuration value to an expected type: %s' % configuration_vars['SYSTEM_ARCH'])


def main():
    """Main entry point"""

    # Parse emageon.conf for configuration values
    configuration_vars = _get_conf_data_as_dict()

    # If an argument is provided it should be the name of the current peer (i.e. mergeeapri or mergeeatest) to override what's in 
    # /etc/emageon.conf. OTherwise get it from the configuration variables in emageon.conf
    try:
        peer_name = sys.argv[1]
    except:
        logging.info('No argument provided on command line. Will read system name from emageon.conf.')
        vip_hostname, vip_domainname, vip_ip, vip_netmask_bits, vip_gateway = _get_netinfo(configuration_vars)
        peer_name = vip_hostname
        peer_domain = vip_domainname

    # Generate a list of servers in this peer
    all_servers_list = _get_servers_in_peer(configuration_vars=configuration_vars)

    # Initialize new classes to set up all of the class definitions, define the metrics, etc.
    metric_objects = _initialize_metric_classes(peer_name=peer_name, peer_domain=peer_domain, server_list=all_servers_list)

    # Start up the http mini-server
    logging.info('Starting http server on port %s' % HOSTING_PORT)
    start_http_server(HOSTING_PORT)

    while True:
        # Start the loop that will refresh the metrics at every polling interval. When the service stop
        # command is issued, isrunning will be updated to be False to break the loop. Note that it will take up
        # to POLLING_INTERVAL_SECONDS to stop the service. So some optimization might be good.
        logging.info('### Starting metric collection for this iteration ###')
        logging.info('Local peer name provided: %s' % peer_name)

        for metric_object in metric_objects:
            try:
                metric_object.fetch()
            except:
                logging.error('Failed to call the fetch() method for object of class %s' % metric_object.__class__.__name__)
                logging.raiseExceptions
                

        logging.info('### End metric collection for this iteration. Sleeping for %s seconds. ###' % POLLING_INTERVAL_SECONDS)
        
        wait_seconds = 0     # reset the counter

        while wait_seconds < POLLING_INTERVAL_SECONDS:
            #time.sleep(POLLING_INTERVAL_SECONDS)
            time.sleep(1)   # check self.isrunning every 1 second to be able to break out the loop faster
            wait_seconds = wait_seconds + 1

    logging.warning('Somehow we have exited the metrics collection loop!')    


if __name__ == "__main__":
    main()