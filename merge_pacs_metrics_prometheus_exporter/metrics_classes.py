"""
Each of the classess that define which metrics to collect and how to collect them are defined here. They are
imported inidividually in the main script
"""
from .config import CONF
from .__init__ import __version__
from datetime import datetime
import logging
import pandas
from prometheus_client import start_http_server, Gauge, Summary, Info, Counter
import re
import requests


# Current software version
CURRENT_VERSION = __version__

class ExporterSelfMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, metric_url, metric_server_label='unknown_merge_pacs_servername', metric_service_name='Merge PACS Process', \
        metric_prefix='merge_pacs_unk', metric_username='', metric_password='', metric_domain='healthpartners'):
        
        logging.info(f'Initializing the {self.__class__.__name__} metric data class')

        # The url where this service's metrics are available
        self.metric_url = metric_url

        # Define the label to use for {server=XXX} labels in each metric. Generally this should be the server's name
        self.server_label = metric_server_label
        
        # Define a service name for clarity in debugging
        self.service_name = metric_service_name

        # Define login information needed to get to the metrics
        self.metric_username = metric_username
        self.metric_password = metric_password
        self.metric_domain = metric_domain
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # Define the unique metrics to collect (labels will be added later)
        logging.info(f'Initializing metrics for {self.service_name}')
        self.i_exporter_version = Info(f'{self.prefix}', f'The version of this prometheus exporter script', ['server', 'version'])

    def fetch(self, http_request_timeout = 2.0):
        """ 
        Connect to the Merge PACS process's metrics page and parse results into Prometheus metrics
        """
        logging.info(f'Gathering metric data for {self.service_name}')

        # Create info metric with version number of this script
        self.i_exporter_version.labels(server=self.server_label, version=CURRENT_VERSION)

        logging.info(f'Done fetching metrics for this polling interval for {self.service_name}')

class MessagingServerAppMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, metric_url, metric_server_label='unknown_merge_pacs_servername', metric_service_name='Merge PACS Process', \
        metric_prefix='merge_pacs_unk', metric_username='', metric_password='', metric_domain='healthpartners'):
        
        logging.info(f'Initializing the {self.__class__.__name__} metric data class')

        # The url where this service's metrics are available
        self.metric_url = metric_url

        # Define the label to use for {server=XXX} labels in each metric. Generally this should be the server's name
        self.server_label = metric_server_label
        
        # Define a service name for clarity in debugging
        self.service_name = metric_service_name

        # Define login information needed to get to the metrics
        self.metric_username = metric_username
        self.metric_password = metric_password
        self.metric_domain = metric_domain
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # Define the unique metrics to collect (labels will be added later)
        logging.info(f'Initializing metrics for {self.service_name}')
        self.g_database_connections = Gauge(f'{self.prefix}_database_connections', f'Active database connections from {self.service_name} service', ['server', 'dbConnectionStatus'])
        self.g_service_uptime = Gauge(f'{self.prefix}_server_uptime', f'Number of hours {self.service_name} has been running since last restart', ['server'])
        self.g_memory_current = Gauge(f'{self.prefix}_memory_current', f'Current memory utilization for various types from {self.service_name}', ['server', 'memoryType'])
        self.g_memory_peak = Gauge(f'{self.prefix}_memory_peak', f'Peak memory utilization for various types from {self.service_name} service', ['server', 'memoryType'])
        self.g_message_counts = Gauge(f'{self.prefix}_message_count', f'Number of messages per queue from the {self.service_name} service', ['server', 'queueName', 'queueType'])
        self.g_service_status = Gauge(f'{self.prefix}_service_status', f'Staus of the {self.service_name} service', ['server'])

    def fetch(self, http_request_timeout = 2.0):
        """ 
        Connect to the Merge PACS process's metrics page and parse results into Prometheus metrics
        """
        logging.info(f'Starting to collect metric data for {self.service_name} from {self.metric_url}')

        self.g_database_connections.clear()
        self.g_service_uptime.clear()
        self.g_memory_current.clear()
        self.g_memory_peak.clear()
        self.g_message_counts.clear()
        self.g_service_status.clear()


        # Get server status page data
        self.g_service_status.labels(server=self.server_label).set(0)

        try:
            r = requests.get(self.metric_url, timeout=http_request_timeout)
            
            # Raise an error if we have a 4XX or 5XX response
            r.raise_for_status()
        except requests.exceptions.Timeout:
            logging.error(f'Timed out getting metrics page {self.metric_url}!')
        except requests.exceptions.HTTPError as httperr:
            logging.error(f'HTTP error getting data from {self.metric_url}! Error: {httperr}')         
        except requests.exceptions.RequestException as rex:
            # Some sort of catastrophic error. bail.
            logging.error(f'Failed getting metrics from {self.metric_url}! Error: {rex}')
        else:
            #set status to one if we can successfully able to get to page
            self.g_service_status.labels(server=self.server_label).set(1)

            ### Parse active and idle database connections
            # self._parse_database_connections(r.text)
            _parse_database_connections(database_connection_metric_obj=self.g_database_connections, server_label=self.server_label, metrics_html=r.text)

            ### Parse service uptime
            # self._parse_service_uptime(r.text)
            _parse_service_uptime(service_uptime_metric_obj=self.g_service_uptime, server_label=self.server_label, metrics_html=r.text)

            ### Parse memory utilization
            # self._parse_memory_utilization(r.text)
            _parse_memory_utilization(memory_current_metric_obj=self.g_memory_current, memory_peak_metric_obj=self.g_memory_peak, \
                server_label=self.server_label, metrics_html=r.text)

            ### Connected clients 
            self._parse_message_counts(r.text)

        logging.info(f'Done fetching metrics for this polling interval for {self.service_name}')

    def _parse_message_counts(self, metrics_html):
        logging.info(f'  Parsing text for message counts metric')
        
        # Clear out the gague metric's previous labels and values. Otherwise if there's no data in this scrape for a particular label combination
        # gague will just report out the most recent value. That's not exactly what we want.
        self.g_message_counts.clear()

        try:
            #pattern = re.compile(r'<TR (class="even")?><TD><a href=.*>(?P<queueName>[\w\-\.]+)</a></TD>\n<TD>(?P<queueType>\w+)</TD>\n<TD>(?P<messageCount>\d+)</TD>\n<TD>(?P<consumerCount>\d+)</TD>\n</TR>')
            # Find the table (should be the only one, but to be safe) containing the term "Message Count"
            # Assumes the table will have columns named "Name", "Type", "Message Count" and "Consumer Count"
            table_list = pandas.read_html(metrics_html, match='Message Count')
            table = table_list[0]
        except:
            logging.warning(f'Failed to parse table of message counts. Not creating metric.')
        else:
            for index, row in table.iterrows():
                if row['Type'] != 'Temp':
                    # Exclude temporary queues with names that are GUIDs
                    self.g_message_counts.labels(server=self.server_label, queueName=row['Name'], queueType=row['Type']).set(row['Message Count'])
                # Not capturing consumer count right now
            logging.info(f'  Metric created for message counts')

class WorklistServerAppMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, metric_url, metric_server_label='unknown_merge_pacs_servername', metric_service_name='Merge PACS Process', \
        metric_prefix='merge_pacs_unk', metric_username='', metric_password='', metric_domain='healthpartners'):
        
        logging.info(f'Initializing the {self.__class__.__name__} metric data class')

        # The url where this service's metrics are available
        self.metric_url = metric_url

        # Define the label to use for {server=XXX} labels in each metric. Generally this should be the server's name
        self.server_label = metric_server_label
        
        # Define a service name for clarity in debugging
        self.service_name = metric_service_name

        # Define login information needed to get to the metrics
        self.metric_username = metric_username
        self.metric_password = metric_password
        self.metric_domain = metric_domain
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # Define the unique metrics to collect (labels will be added later)
        logging.info(f'Initializing metrics from the {self.service_name} service')
        self.g_database_connections = Gauge(f'{self.prefix}_database_connections', f'Active database connections from {self.service_name} service', ['server', 'dbConnectionStatus'])
        self.g_service_uptime = Gauge(f'{self.prefix}_server_uptime', f'Number of hours {self.service_name} has been running since last restart', ['server'])
        self.g_memory_current = Gauge(f'{self.prefix}_memory_current', f'Current memory utilization for various types from {self.service_name}', ['server', 'memoryType'])
        self.g_memory_peak = Gauge(f'{self.prefix}_memory_peak', f'Peak memory utilization for various types from {self.service_name} service', ['server', 'memoryType'])
        self.g_connected_clients = Gauge(f'{self.prefix}_connected_clients', f'Number of connected clients from {self.service_name} service', ['server'])
        self.g_active_worklists = Gauge(f'{self.prefix}_active_worklists', f'Active worklists by status from {self.service_name} service', ['server', 'worklistStatus'])
        self.g_exam_cache_loaded = Gauge(f'{self.prefix}_exam_cache_loaded', f'Number of cached exams currently loaded by {self.service_name} service', ['server'])
        self.g_exam_cache_stale = Gauge(f'{self.prefix}_exam_cache_stale', f'Number of stale cached exams by {self.service_name} service', ['server'])
        self.g_exam_cache_loads_total = Gauge(f'{self.prefix}_exam_cache_total_loads', f'Number of total cached exams loaded by {self.service_name} service since startup', ['server'])
        self.g_pending_jobs = Gauge(f'{self.prefix}_pending_jobs', f'Pending jobs by type from {self.service_name} service', ['server', 'pendingJobType'])
        self.g_service_status = Gauge(f'{self.prefix}_service_status', f'Staus of the {self.service_name} service', ['server'])

    def fetch(self, http_request_timeout = 2.0):
        """ 
        Connect to the Merge PACS process's metrics page and parse results into Prometheus metrics
        """
        logging.info(f'Starting to collect metric data for {self.service_name} from {self.metric_url}')

        self.g_database_connections.clear()
        self.g_service_uptime.clear()
        self.g_memory_current.clear()
        self.g_memory_peak.clear()
        self.g_connected_clients.clear()
        self.g_active_worklists.clear()
        self.g_exam_cache_loaded.clear()
        self.g_exam_cache_stale.clear()
        self.g_exam_cache_loads_total.clear()
        self.g_pending_jobs.clear()
        self.g_service_status.clear()
 

        # Get server status page data
        self.g_service_status.labels(server=self.server_label).set(0)
        try:
            r = requests.get(self.metric_url, timeout=http_request_timeout)
            
            # Raise an error if we have a 4XX or 5XX response
            r.raise_for_status()
        except requests.exceptions.Timeout:
            logging.error(f'Timed out getting metrics page {self.metric_url}!')
        except requests.exceptions.HTTPError as httperr:
            logging.error(f'HTTP error getting data from {self.metric_url}! Error: {httperr}')
        except requests.exceptions.RequestException as rex:
            # Some sort of catastrophic error. bail.
            logging.error(f'Failed getting metrics from {self.metric_url}! Error: {rex}')
        else:
            #set status to one if we can successfully able to get to page
            self.g_service_status.labels(server=self.server_label).set(1)
            
            ### Parse active and idle database connections
            # self._parse_database_connections(r.text)
            _parse_database_connections(database_connection_metric_obj=self.g_database_connections, server_label=self.server_label, metrics_html=r.text)

            ### Parse service uptime
            # self._parse_service_uptime(r.text)
            _parse_service_uptime(service_uptime_metric_obj=self.g_service_uptime, server_label=self.server_label, metrics_html=r.text)

            ### Parse memory utilization
            # self._parse_memory_utilization(r.text)
            _parse_memory_utilization(memory_current_metric_obj=self.g_memory_current, memory_peak_metric_obj=self.g_memory_peak, \
                server_label=self.server_label, metrics_html=r.text)

            ### Connected clients 
            self._parse_connected_clients(r.text)

            ### Active worklists
            self._parse_active_worklists(r.text)

            ### Exam Cache
            self._parse_exam_cache(r.text)

            ### Pending Jobs
            self._parse_pending_jobs(r.text)

        logging.info(f'Done fetching metrics for this polling interval for {self.service_name}')

    def _parse_connected_clients(self, metrics_html):
        try:
            logging.info(f'  Parsing text for connected clients metric')
            pattern = re.compile(r'clients: <B>(?P<connected_clients>\d*)</B>')
            match = re.search(pattern, metrics_html)
            connected_clients = match.group('connected_clients')
        except:
            logging.warning(f'Failed to match the pattern for connected clients. Not creating metric.')
        else:
            self.g_connected_clients.labels(server=self.server_label).set(connected_clients)
            logging.info(f'  Metric created for connected clients')

    def _parse_active_worklists(self, metrics_html):
        try:
            logging.info(f'  Parsing text for active worklists metric')
            pattern = re.compile(r'Active worklists: <B>(?P<loaded>\d+) loaded, (?P<loading>\d+) loading, (?P<selecting>\d+) selecting, (?P<waiting>\d+) ')
            match = re.search(pattern, metrics_html)
            #loaded = match.group('loaded')
            #loading = match.group('loading')
            #selecting = match.group('selecting')
            #waiting = match.group('waiting')
        except:
            logging.warning(f'Failed to match the pattern for active worklists. Not creating metric.')
        else:
            for worklistStatus, val in match.groupdict().items():
                self.g_active_worklists.labels(server=self.server_label, worklistStatus=worklistStatus).set(val)
            logging.info(f'  Metrics created for active worklist')

    def _parse_exam_cache(self, metrics_html):
        try:
            logging.info(f'  Parsing text for exam cache metrics')
            pattern = re.compile(r'Loaded exams: (?P<loaded_exams>\d+) .*. Stale exams: (?P<stale_exams>\d+). Exam loads: (?P<exam_loads>\d+) ')
            match = re.search(pattern, metrics_html)
            loaded_exams = match.group('loaded_exams')
            stale_exams = match.group('stale_exams')
            total_loaded = match.group('exam_loads')
        except:
            logging.warning(f'Failed to match the pattern for exam cache. Not creating metrics.')
        else:
            self.g_exam_cache_loaded.labels(server=self.server_label).set(loaded_exams)
            self.g_exam_cache_stale.labels(server=self.server_label).set(stale_exams)
            self.g_exam_cache_loads_total.labels(server=self.server_label).set(total_loaded)
            logging.info(f'  Metrics created for exam cache')

    def _parse_pending_jobs(self, metrics_html):
        try:
            logging.info(f'  Parsing text for pending jobs metrics')
            pattern = re.compile(r'Pending jobs</a> - Exam requests: (?P<exam_requests>\d+). Patient updates: (?P<patient_updates>\d+). Order updates: (?P<order_updates>\d+). Study updates: (?P<study_updates>\d+). Status updates: (?P<status_updates>\d+). Instance count updates: (?P<instance_count_updates>\d+). Custom tag updates: (?P<custom_tag_updates>\d+)')
            match = re.search(pattern, metrics_html)
        except:
            logging.warning(f'Failed to match the pattern for pending jobs. Not creating metrics.')
        else:
            for job_type, val in match.groupdict().items():
                self.g_pending_jobs.labels(server=self.server_label, pendingJobType=job_type).set(val)
            logging.info(f'  Metrics created for pending jobs')

class ClientMessagingServerAppMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, metric_url, metric_server_label='unknown_merge_pacs_servername', metric_service_name='Merge PACS Process', \
        metric_prefix='merge_pacs_unk', metric_username='', metric_password='', metric_domain='healthpartners'):
        
        logging.info(f'Initializing the {self.__class__.__name__} metric data class')

        # The url where this service's metrics are available
        self.metric_url = metric_url

        # Define the label to use for {server=XXX} labels in each metric. Generally this should be the server's name
        self.server_label = metric_server_label
        
        # Define a service name for clarity in debugging
        self.service_name = metric_service_name

        # Define login information needed to get to the metrics
        self.metric_username = metric_username
        self.metric_password = metric_password
        self.metric_domain = metric_domain
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # Define the unique metrics to collect (labels will be added later)
        logging.info(f'Initializing metrics for {self.service_name}')

        self.g_active_users = Gauge(f'{self.prefix}_active_users', f'Active Merge PACS users from the {self.service_name} service)', ['server'])
        self.g_service_status = Gauge(f'{self.prefix}_service_status', f'Staus of the {self.service_name} service', ['server'])

    def fetch(self, http_request_timeout=2):
        """ 
        Connect to the Merge PACS process's metrics page and parse results into Prometheus metrics
        """
        logging.info(f'Starting to collect metric data for {self.service_name} from {self.metric_url}')

        #clear old metrics
        self.g_active_users.clear()
        self.g_service_status.clear()

        # Get server status page data
        self.g_service_status.labels(server=self.server_label).set(0)
        try:
            r = requests.get(self.metric_url, timeout=http_request_timeout)
            
            # Raise an error if we have a 4XX or 5XX response
            r.raise_for_status()
        except requests.exceptions.Timeout:
            logging.error(f'Timed out getting metrics page {self.metric_url}!')
        except requests.exceptions.HTTPError as httperr:
            logging.error(f'HTTP error getting data from {self.metric_url}! Error: {httperr}')
        except requests.exceptions.RequestException as rex:
            # Some sort of catastrophic error. bail.
            logging.error(f'Failed getting metrics from {self.metric_url}! Error: {rex}')
        else:
            #set status to one if we can successfully able to get to page
            self.g_service_status.labels(server=self.server_label).set(1) 
            
            ### Parse results for Active and Idle DB connections
            self._parse_active_users(r.text)

        logging.info(f'Done fetching metrics for this polling interval for {self.service_name}')

    def _parse_active_users(self, metrics_html):
        try:
            logging.info(f'  Parsing text for active users metric')
            pattern = re.compile(r'Active pipelines:<B> (?P<active_users>\d+)')
            match = re.search(pattern, metrics_html)
            active_users = match.group('active_users')
        except:
            # Failed to match patterns as expected
            logging.warning(f'Failed to match the pattern for database connections. Not creating metric.')
        else:
            # Populate Metric
            self.g_active_users.labels(server=self.server_label).set(active_users)
            logging.info(f'  Metrics created for active users')

class ApplicationServerAppMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, metric_url, metric_server_label='unknown_merge_pacs_servername', metric_service_name='Merge PACS Process', \
        metric_prefix='merge_pacs_unk', metric_username='', metric_password='', metric_domain=''):
        
        logging.info(f'Initializing the {self.__class__.__name__} metric data class')

        # The url where this service's metrics are available
        self.metric_url = metric_url

        # Define the label to use for {server=XXX} labels in each metric. Generally this should be the server's name
        self.server_label = metric_server_label
        
        # Define a service name for clarity in debugging
        self.service_name = metric_service_name

        # Define login information needed to get to the metrics
        self.metric_username = metric_username
        self.metric_password = metric_password
        self.metric_domain = metric_domain
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # This persistent variable will help us figure out which rows are added since the last time we scraped the page
        self.previous_data_scrape_time = datetime.now()

        # Define the unique metrics to collect (labels will be added later)
        logging.info(f'Initializing metrics for {self.service_name}')

        self.g_database_connections = Gauge(f'{self.prefix}_database_connections', f'Database connections from the {self.service_name} service', ['server', 'dbConnectionStatus'])
        self.g_service_uptime = Gauge(f'{self.prefix}_server_uptime', f'Number of hours {self.service_name} has been running since last restart', ['server'])
        self.g_memory_current = Gauge(f'{self.prefix}_memory_current', f'Current memory utilization for various types from {self.service_name} service', ['server', 'memoryType'])
        self.g_memory_peak = Gauge(f'{self.prefix}_memory_peak', f'Peak memory utilization for various types from {self.service_name} service', ['server', 'memoryType'])
        self.s_query_duration = Summary(f'{self.prefix}_query_duration_seconds', f'Query duration by query type for the {self.service_name} service', ['server', 'queryType'])
        self.g_service_status = Gauge(f'{self.prefix}_service_status', f'Staus of the {self.service_name} service', ['server'])


    def fetch(self, http_request_timeout=2):
        """ 
        Connect to the Merge PACS process's metrics page and parse results into Prometheus metrics
        """
        logging.info(f'Starting to collect metric data for {self.service_name} from {self.metric_url}')

        # Quick note here: The Application Service takes so long to open and scrape that we need to avoid
        # clearing current metric values at the beginning of this function. Otherwise there are several seconds 
        # when the value is cleared and the new value is not yet populated. This leads to missing data if the time
        # aligns with the scrape interval, which happens frequently.
        #
        # Instead, plan to clear current values in an 'except' block in case the metrics collection attempt fails.
        
        #clear old metrics
        #self.g_database_connections.clear()
        #self.g_service_uptime.clear()
        #self.g_memory_current.clear()
        #self.g_memory_peak.clear()
        #self.s_query_duration.clear()
        #self.g_service_status.clear()

        # Get server status page data
        #self.g_service_status.labels(server=self.server_label).set(0)
        
        try:
            # This page requires authentication, construct the payload with login informaiton and start a session
            payload = {'amicasUsername': self.metric_username, 
                        'password': self.metric_password,
                        'domain': self.metric_domain,
                        'submitButton': 'Login'
                    }
            session = requests.Session()
            # Post the payload to the login page to get authenticated  (note could maybe check if this is needed before posting?)
            r_post = session.post(self.metric_url, data=payload)
            # re-request page now that we're authenticated
            r = session.get(self.metric_url, timeout=http_request_timeout)
            
            # Raise an error if we have a 4XX or 5XX response
            r.raise_for_status()
        except requests.exceptions.Timeout:
            logging.error(f'Timed out getting metrics page {self.metric_url}!')
            self.g_service_status.labels(server=self.server_label).set(0)
        except requests.exceptions.HTTPError as httperr:
            logging.error(f'HTTP error getting data from {self.metric_url}! Error: {httperr}')
            self.g_service_status.labels(server=self.server_label).set(0)
        except requests.exceptions.RequestException as rex:
            # Some sort of catastrophic error. bail.
            logging.error(f'Failed getting metrics from {self.metric_url}! Error: {rex}')
            self.g_service_status.labels(server=self.server_label).set(0)
        except Exception as err:
            logging.error(f'An error occurred getting data for the Application Server service. Error: {err}')
            self.g_service_status.labels(server=self.server_label).set(0)
        else:

            #set status to one if we can successfully able to get to page
            self.g_service_status.labels(server=self.server_label).set(1)

            # Update with the current time since we just we scraped data. Next around we can process any data added since this scrape.
            self.current_data_scrape_time = datetime.now()

            ### Parse database connections
            # self._parse_database_connections(r.text)
            _parse_database_connections(database_connection_metric_obj=self.g_database_connections, server_label=self.server_label, metrics_html=r.text)

            ### Parse service uptime
            # self._parse_service_uptime(r.text)
            _parse_service_uptime(service_uptime_metric_obj=self.g_service_uptime, server_label=self.server_label, metrics_html=r.text)

            ### Parse memory utilization
            # self._parse_memory_utilization(r.text)
            _parse_memory_utilization(memory_current_metric_obj=self.g_memory_current, memory_peak_metric_obj=self.g_memory_peak, \
                server_label=self.server_label, metrics_html=r.text)

            ### Parse average query duration
            self._parse_average_query_duration(r.text)

            # Update previous data scrape time placeholder
            self.previous_data_scrape_time = self.current_data_scrape_time

        logging.info(f'Done fetching metrics for this polling interval for {self.service_name}')

    def _parse_average_query_duration(self, metrics_html):
        logging.info(f'  Parsing text for average query duration metric')
        
        # Determine if the scrape for new data was successful or not but updating this variable
        avg_query_duration_metric_found = False

        try:
            # Find the table (should be the only one, but to be safe) containing the term "<TH><B>Filters</B></TH>"
            # Assumes the table will have columns named "ID", "Status", "Type", "Priority", "User", "Results", "Duration", "Start Time", "Wait Time", "Filters"
            # breakpoint()
            search_tables_for_text = 'Filters'
            table_dfs = pandas.read_html(metrics_html, match=search_tables_for_text)
            table_df = table_dfs[0]

            # Convert Start Time column in to Python datetime
            table_df['Start Time'] = pandas.to_datetime(table_df['Start Time'])
        except Exception as err:
            logging.warning(f'  Failed to find a table with the term "{search_tables_for_text}" to get message counts. Clearing previous values. Error: {err}')
        else:
            pattern = re.compile(r'(?P<duration>\d+) (?P<unit>(ms|s))')  # Pattern that will match either "1 s" or "123 ms" in Duration column
            # create a smaller dataframe where only rows that have a Start Time more recent than the last time we scraped data are included
            recent_queries_df = table_df.loc[table_df['Start Time'] > self.previous_data_scrape_time]
            logging.info(f'    Identified {len(recent_queries_df.index)} rows of query data more recent than {self.previous_data_scrape_time}')
            for index, row in recent_queries_df.iterrows():
                #query_duration_str = row['Duration']
                match = re.search(pattern, row['Duration'])
                #breakpoint()
                try:
                    duration = int(match.group('duration'))
                    unit = match.group('unit')
                    if unit == 'ms':
                        query_duration_s = duration / 1000
                    else:
                        query_duration_s = duration
                except:
                    # The duration format isn't recognized
                    logging.warning(f'  Failed to parse the duration format for string: {row["Duration"]}')
                else:
                    # Add observation to summary metric
                    avg_query_duration_metric_found = True

        if avg_query_duration_metric_found:
            self.s_query_duration.labels(server=self.server_label, queryType=row['Type']).observe(query_duration_s)
        else:
            self.s_query_duration.clear()
                
            logging.info(f'  Metric created for average query duration (if there is any recent data)')

class EANotificationProcessorAppMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, metric_url, metric_server_label='unknown_merge_pacs_servername', metric_service_name='Merge PACS Process', \
        metric_prefix='merge_pacs_unk', metric_username='', metric_password='', metric_domain='healthpartners'):
        
        logging.info(f'Initializing the {self.__class__.__name__} metric data class')

        # The url where this service's metrics are available
        self.metric_url = metric_url

        # Define the label to use for {server=XXX} labels in each metric. Generally this should be the server's name
        self.server_label = metric_server_label
        
        # Define a service name for clarity in debugging
        self.service_name = metric_service_name

        # Define login information needed to get to the metrics
        self.metric_username = metric_username
        self.metric_password = metric_password
        self.metric_domain = metric_domain
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # Define the unique metrics to collect (labels will be added later)
        logging.info(f'Initializing metrics for {self.service_name}')
        self.g_database_connections = Gauge(f'{self.prefix}_database_connections', f'Database connections from the {self.service_name} service', ['server', 'dbConnectionStatus'])
        self.g_service_uptime = Gauge(f'{self.prefix}_server_uptime', f'Number of hours {self.service_name} has been running since last restart', ['server'])
        self.g_memory_current = Gauge(f'{self.prefix}_memory_current', f'Current memory utilization for various types from {self.service_name} service', ['server', 'memoryType'])
        self.g_memory_peak = Gauge(f'{self.prefix}_memory_peak', f'Peak memory utilization for various types from {self.service_name} service', ['server', 'memoryType'])

        self.g_active_studies = Gauge(f'{self.prefix}_active_studies', f'Studies currently being processed by the {self.service_name} service', ['server'])
        self.g_studies_processed_total = Gauge(f'{self.prefix}_studies_processed_total', f'Number of studies processed since service startup by the {self.service_name} service', ['server'])
        self.g_images_processed_total = Gauge(f'{self.prefix}_images_processed_total', f'Number of images processed since service startup by the {self.service_name} service', ['server'])

        self.g_jms_sender_connection = Gauge(f'{self.prefix}_jms_sender_connection', f'Active JMS sender connections in use by the {self.service_name} service', ['server'])
        self.g_jms_receiver_connection = Gauge(f'{self.prefix}_jms_receiver_connection', f'Active JMS receiver connections in use by the {self.service_name} service', ['server'])
        self.g_jms_sender_sessions = Gauge(f'{self.prefix}_jms_sender_sessions', f'Active JMS sender sessions in use by the {self.service_name} service', ['server'])
        self.g_jms_receiver_sessions = Gauge(f'{self.prefix}_jms_receiver_sessions', f'Active JMS receiver sessions in use by the {self.service_name} service', ['server'])

        self.g_active_studies_idletime_max = Gauge(f'{self.prefix}_studies_idletime_max', f'Max idle time of all studies currently active in the {self.service_name} service', ['server'])
        self.g_active_studies_idletime_avg = Gauge(f'{self.prefix}_studies_idletime_avg', f'Average idle time of all studies currently active in the {self.service_name} service', ['server'])
        
        self.g_received_notifications = Gauge(f'{self.prefix}_received_notifications', f'Notifications received from the EA by the {self.service_name} service in Merge PACS since last service restart', \
            ['server', 'notificationType'])
        self.g_jobs_constructed = Gauge(f'{self.prefix}_jobs_constructed', f'Jobs constructed recently(?) by the {self.service_name} service', ['server'])
        self.g_jobs_being_constructed = Gauge(f'{self.prefix}_jobs_being_constructed', f'Jobs currently being constructed by the {self.service_name} service', ['server'])
        self.g_jobs_waiting_for_locks = Gauge(f'{self.prefix}_jobs_waiting_for_locks', f'Jobs waiting for locks before they can be processed by the {self.service_name} service', ['server'])
        self.g_jobs_blocked = Gauge(f'{self.prefix}_jobs_blocked', f'Jobs blocked that cannot currently begin processing in the {self.service_name} service', ['server'])
        self.g_jobs_dispatched = Gauge(f'{self.prefix}_jobs_dispatched', f'Jobs queued to be dispatched by the {self.service_name} service', ['server'])
        self.g_dispatched_jobs_queued = Gauge(f'{self.prefix}_dispatched_jobs_queued', f'Number of jobs constructed recently(?) by the {self.service_name} service', ['server'])
        self.g_studies_locked = Gauge(f'{self.prefix}_studies_locked', f'Number of studies currently locked by the {self.service_name} service', ['server'])
        self.g_expected_instances = Gauge(f'{self.prefix}_expected_instances', f'Expected number of instances(?) in the {self.service_name} service', ['server'])
        self.g_expected_events = Gauge(f'{self.prefix}_expected_events', f'Expected number of events(?) in the {self.service_name} service', ['server'])
        self.g_service_status = Gauge(f'{self.prefix}_service_status', f'Staus of the {self.service_name} service', ['server'])

    def fetch(self, http_request_timeout = 2.0):
        """ 
        Connect to the Merge PACS process's metrics page and parse results into Prometheus metrics
        """
        logging.info(f'Starting to collect metric data for {self.service_name} from {self.metric_url}')

        #clear old metrics
        self.g_database_connections.clear()
        self.g_service_uptime.clear()
        self.g_memory_current.clear()
        self.g_memory_peak.clear()
        self.g_active_studies.clear()
        self.g_studies_processed_total.clear()
        self.g_images_processed_total.clear()
        self.g_jms_sender_connection.clear()
        self.g_jms_receiver_connection.clear()
        self.g_jms_sender_sessions.clear()
        self.g_jms_receiver_sessions.clear()
        self.g_active_studies_idletime_max.clear()
        self.g_active_studies_idletime_avg.clear()
        self.g_received_notifications.clear()
        self.g_jobs_constructed.clear()
        self.g_jobs_being_constructed.clear()
        self.g_jobs_waiting_for_locks.clear()
        self.g_jobs_blocked.clear()
        self.g_jobs_dispatched.clear()
        self.g_studies_locked.clear()
        self.g_expected_instances.clear()
        self.g_expected_events.clear()
        self.g_service_status.clear()


        # Get server status page data
        self.g_service_status.labels(server=self.server_label).set(0)
        try:
            r = requests.get(self.metric_url, timeout=http_request_timeout)
            
            # Raise an error if we have a 4XX or 5XX response
            r.raise_for_status()
        except requests.exceptions.Timeout:
            logging.error(f'Timed out getting metrics page {self.metric_url}!')
        except requests.exceptions.HTTPError as httperr:
            logging.error(f'HTTP error getting data from {self.metric_url}! Error: {httperr}')
        except requests.exceptions.RequestException as rex:
            # Some sort of catastrophic error. bail.
            logging.error(f'Failed getting metrics from {self.metric_url}! Error: {rex}')
        else:
            #set status to one if we can successfully able to get to page
            self.g_service_status.labels(server=self.server_label).set(1) 

            ### Parse active and idle database connections
            _parse_database_connections(database_connection_metric_obj=self.g_database_connections, server_label=self.server_label, metrics_html=r.text)

            ### Parse service uptime
            _parse_service_uptime(service_uptime_metric_obj=self.g_service_uptime, server_label=self.server_label, metrics_html=r.text)

            ### Parse memory utilization
            _parse_memory_utilization(memory_current_metric_obj=self.g_memory_current, memory_peak_metric_obj=self.g_memory_peak, \
                server_label=self.server_label, metrics_html=r.text)

            ### Received notifications 
            self._parse_received_notifications(r.text)

            ### Received notification manager jobs counts data
            self._parse_notification_manager(r.text)

            ### Parse active studies counts
            self._parse_active_studies_counts(r.text)

            ### Parse JMS sender and receiver counts
            self._parse_jms_connection_counts(r.text)
            
            ### Parse active studies idle time stats
            self._parse_active_studies_idle_times(r.text)
            
        logging.info(f'Done fetching metrics for this polling interval for {self.service_name}')

    def _parse_received_notifications(self, metrics_html):
        logging.info(f'  Parsing text for received notifications metrics')
        try:
            # Find the table (should be the only one, but to be safe) containing the term "Instance Notifications"
            # breakpoint()
            search_tables_for_text = 'Instance Notifications'
            table_dfs = pandas.read_html(metrics_html, match=search_tables_for_text)
            table_df = table_dfs[0]

            # Convert Start Time column in to Python datetime
            # table_df['Start Time'] = pandas.to_datetime(table_df['Start Time'])
        except:
            logging.warning(f'  Failed to find a table with the term "{search_tables_for_text}" to get received notification counts. Not creating metric.')
        else:
            for column in table_df:
                try:
                    # Lower case all text and replace spaces with "_"
                    normalized_col_name = column.lower().replace(" ","_")
                    # This table only has one row of data, so grab values from the first data row
                    col_value = table_df[column][0]
                except:
                    # The duration format isn't recognized
                    logging.warning(f'  Failed to parse column name and value for {column}')
                else:
                    # Add observation to summary metric
                    self.g_received_notifications.labels(server=self.server_label, notificationType=normalized_col_name).set(col_value)
                
            logging.info(f'  Metrics created for received notifications')
            
    def _parse_notification_manager(self, metrics_html):
        logging.info(f'  Parsing text for notification manager metrics')
        expected_column_names = ["Jobs Constructed", "Jobs being Constructed", "Jobs Waiting for Locks", "Jobs Blocked", \
            "Jobs Dispatched", "Dispatched Jobs Queued", "Studies Locked", "Expected Instances", "Expected Events"]

        # This function will parse 9 different columns from the same table, so we need to map which columns end up in which metrics.
        # This dict maps the column names (header values in the table) to the associated metric object
        column_name_to_metric_obj_dict = {
            'Jobs Constructed' :        self.g_jobs_constructed,
            'Jobs being Constructed' :  self.g_jobs_being_constructed,
            'Jobs Waiting for Locks' :  self.g_jobs_waiting_for_locks,
            'Jobs Blocked' :            self.g_jobs_blocked,
            'Jobs Dispatched' :         self.g_jobs_dispatched, 
            'Dispatched Jobs Queued' :  self.g_dispatched_jobs_queued,
            'Studies Locked' :          self.g_studies_locked,
            'Expected Instances' :      self.g_expected_instances,
            'Expected Events' :         self.g_expected_events
        }

        # Find the table (should be the only one, but to be safe) containing the term "Jobs Constructed"
        search_tables_for_text = 'Jobs Constructed'
        try:
            # This parsing assumes that column names are: "Jobs Constructed", "Jobs being Constructed", "Jobs Waiting for Locks", "Jobs Blocked", 
            # "Jobs Dispatched", "Dispatched Jobs Queued", "Studies Locked", "Expected Instances", "Expected Events"
            # breakpoint()
            table_dfs = pandas.read_html(metrics_html, match=search_tables_for_text)
            table_df = table_dfs[0]
        except:
            logging.warning(f'  Failed to find a table with the term "{search_tables_for_text}" to get notification manager counts. Not creating metric.')
        else:
            for column_name in column_name_to_metric_obj_dict:
                try:
                    this_metric_obj = column_name_to_metric_obj_dict[column_name]
                    column_val = table_df[column_name][0]  # There's only one row in table, so always use row 0

                except:
                    # The duration format isn't recognized
                    logging.warning(f'  Failed to parse column name and value for {column_name}')
                else:
                    # Add observation to summary metric
                    this_metric_obj.labels(server=self.server_label).set(column_val)      
                
            logging.info(f'  Metrics created for notification manager')

    def _parse_active_studies_counts(self, metrics_html):
        logging.info(f'  Parsing text for active studies and images metrics')
        try:
            # Parse active studies and number of images and studies processed since startup
            #Example: <DIV CLASS="ActiveStudiesAndImages">Active studies:<B>31</B>,&nbsp;Processed since startup:<B>3790756</B> images / <B>51263</B> studies
            match = re.search(r'Active studies:<B>(?P<active_studies>\d*)<\/B>.*Processed since startup:<B>(?P<images_processed>\d*)<\/B> images \/ <B>(?P<studies_processed>\d*)<\/B> studies', metrics_html)

            active_studies = int(match.group('active_studies'))
            images_processed = int(match.group('images_processed'))
            studies_processed = int(match.group('studies_processed'))

            # Convert Start Time column in to Python datetime
            # table_df['Start Time'] = pandas.to_datetime(table_df['Start Time'])
        except:
            logging.warning(f'  Failed to parse active studies and images counts. Not creating metrics.')
        else:
            self.g_active_studies.labels(server=self.server_label).set(active_studies)
            self.g_studies_processed_total.labels(server=self.server_label).set(studies_processed)
            self.g_images_processed_total.labels(server=self.server_label).set(images_processed)
                
            logging.info(f'  Metrics created for active studies and images counts')

    def _parse_jms_connection_counts(self, metrics_html):
        logging.info(f'  Parsing text for JMS connection metrics')
        try:
            # Parse JMS sender and receiver connection counts
            # EXAMPLE: <p><p><p><b>INTERNAL JMS Manager</b></p>Sender connection: 1<br>Receiver connection: 1<p/>...
            match = re.search(r'INTERNAL JMS Manager.*Sender connection: (?P<jms_sender_connection>\d+)<br>Receiver connection: (?P<jms_receiver_connection>\d+)', metrics_html)

            jms_sender_connection = match.group('jms_sender_connection')
            jms_receiver_connection = match.group('jms_receiver_connection')
        except:
            logging.warning(f'  Failed to parse JMS connection counts counts. Not creating metrics.')
        else:
            self.g_jms_sender_connection.labels(server=self.server_label).set(jms_sender_connection)
            self.g_jms_receiver_connection.labels(server=self.server_label).set(jms_receiver_connection)
        
        try:
            # Parse JMS sender and receiver session counts
            match = re.search(r'JMS Sender Sessions\((?P<jms_sender_sessions>\d*)\)', metrics_html)
            jms_sender_sessions = match.group('jms_sender_sessions')

            match = re.search(r'Receiver Sessions</b>\((?P<jms_receiver_sessions>\d*)\)', metrics_html)
            jms_receiver_sessions = match.group('jms_receiver_sessions')
        except:
            logging.warning(f'  Failed to parse JMS session counts. Not creating metrics.')
        else:
            self.g_jms_sender_sessions.labels(server=self.server_label).set(jms_sender_sessions)
            self.g_jms_receiver_sessions.labels(server=self.server_label).set(jms_receiver_sessions)

            logging.info(f'  Metrics created for JMS sender and receiver notifications')

    def _parse_active_studies_idle_times(self, metrics_html):
        logging.info(f'  Parsing active studies idle times metrics')
        try:
            # Parse JMS sender and receiver connection counts
            table_dfs = pandas.read_html(metrics_html, match='Patient Name', header=0)
            table_df = table_dfs[0] # There should only be one matching table anyway, but take the first one anyway
            max_time = table_df['Idle Time'].max()
            mean_time = table_df['Idle Time'].mean()
        except:
            logging.warning(f'  Failed to parse column name and values for average and max idle times')
        else:
            self.g_active_studies_idletime_max.labels(server=self.server_label).set(max_time)
            self.g_active_studies_idletime_avg.labels(server=self.server_label).set(mean_time)
            logging.info(f'  Metrics created for JMS sender and receiver notifications')

class SchedulerAppMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, metric_url, metric_server_label='unknown_merge_pacs_servername', metric_service_name='Merge PACS Process', \
        metric_prefix='merge_pacs_unk', metric_username='', metric_password='', metric_domain='healthpartners'):
        
        logging.info(f'Initializing the {self.__class__.__name__} metric data class')

        # The url where this service's metrics are available
        self.metric_url = metric_url

        # Define the label to use for {server=XXX} labels in each metric. Generally this should be the server's name
        self.server_label = metric_server_label
        
        # Define a service name for clarity in debugging
        self.service_name = metric_service_name

        # Define login information needed to get to the metrics
        self.metric_username = metric_username
        self.metric_password = metric_password
        self.metric_domain = metric_domain
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # Define the unique metrics to collect (labels will be added later)
        logging.info(f'Initializing metrics for {self.service_name}')
        self.g_database_connections = Gauge(f'{self.prefix}_database_connections', f'Database connections from the {self.service_name} service', ['server', 'dbConnectionStatus'])
        self.g_service_uptime = Gauge(f'{self.prefix}_server_uptime', f'Number of hours {self.service_name} has been running since last restart', ['server'])
        self.g_memory_current = Gauge(f'{self.prefix}_memory_current', f'Current memory utilization for various types from {self.service_name} service', ['server', 'memoryType'])
        self.g_memory_peak = Gauge(f'{self.prefix}_memory_peak', f'Peak memory utilization for various types from {self.service_name} service', ['server', 'memoryType'])

        self.g_active_threads = Gauge(f'{self.prefix}_active_threads', f'Jobs by status in the {self.service_name} service', \
            ['server', 'command', 'jobStatus']) # Where jobStatus is one of: procssed, queued, wait, failed, or selected (values in columns 1-3 in the table)
        self.g_jobs_blocked = Gauge(f'{self.prefix}_jobs_blocked', f'Jobs that are blocked from processing in the {self.service_name} service', ['server']) # This is a separate value from the above measures
        self.g_service_status = Gauge(f'{self.prefix}_service_status', f'Staus of the {self.service_name} service', ['server'])

    def fetch(self, http_request_timeout = 2.0):
        """ 
        Connect to the Merge PACS process's metrics page and parse results into Prometheus metrics
        """
        logging.info(f'Starting to collect metric data for {self.service_name} from {self.metric_url}')
        
        
        #clear old metrics
        self.g_database_connections.clear()
        self.g_service_uptime.clear()
        self.g_memory_current.clear()
        self.g_memory_peak.clear()
        self.g_active_threads.clear()
        self.g_jobs_blocked.clear()
        self.g_service_status.clear()


        # Get server status page data
        self.g_service_status.labels(server=self.server_label).set(0)
        try:
            r = requests.get(self.metric_url, timeout=http_request_timeout)
            
            # Raise an error if we have a 4XX or 5XX response
            r.raise_for_status()
        except requests.exceptions.Timeout:
            logging.error(f'Timed out getting metrics page {self.metric_url}!')
        except requests.exceptions.HTTPError as httperr:
            logging.error(f'HTTP error getting data from {self.metric_url}! Error: {httperr}')
        except requests.exceptions.RequestException as rex:
            # Some sort of catastrophic error. bail.
            logging.error(f'Failed getting metrics from {self.metric_url}! Error: {rex}')
        else:
            #set status to one if we can successfully able to get to page
            self.g_service_status.labels(server=self.server_label).set(1)
            
            
            ### Parse active and idle database connections
            # self._parse_database_connections(r.text)
            _parse_database_connections(database_connection_metric_obj=self.g_database_connections, server_label=self.server_label, metrics_html=r.text)

            ### Parse service uptime
            # self._parse_service_uptime(r.text)
            _parse_service_uptime(service_uptime_metric_obj=self.g_service_uptime, server_label=self.server_label, metrics_html=r.text)

            ### Parse memory utilization
            # self._parse_memory_utilization(r.text)
            _parse_memory_utilization(memory_current_metric_obj=self.g_memory_current, memory_peak_metric_obj=self.g_memory_peak, \
                server_label=self.server_label, metrics_html=r.text)

            ### Active threads 
            self._parse_active_threads(r.text)

            ### Jobs blocked
            self._parse_jobs_blocked(r.text)

        logging.info(f'Done fetching metrics for this polling interval for {self.service_name}')

    def _parse_active_threads(self, metrics_html):
        logging.info(f'  Parsing text for active threads metrics')
        
        # Clear out the gague metric's previous labels and values. Otherwise if there's no data in this scrape for a particular label combination
        # gague will just report out the most recent value. That's not exactly what we want.
        self.g_active_threads.clear()

        try:
            # Find the table (should be the only one, but to be safe) containing the term "Instance Notifications"
            # breakpoint()
            search_tables_for_text = 'Command'
            table_dfs = pandas.read_html(metrics_html, match=search_tables_for_text)
            table_df = table_dfs[0]
            #table_df.set_index('Command')

        except:
            logging.warning(f'  Failed to find a table with the term "{search_tables_for_text}" to get received notification counts. Not creating metric.')
        else:
            for index, row in table_df.iterrows():
                try:
                    jobs_processed = int(row['Jobs Processed']) # Sometimes this value is "-", so don't assign a value for now if so
                except:
                    logging.warning(f'  Failed to parse "Jobs Processed" for row: {row}')
                else:
                    self.g_active_threads.labels(server=self.server_label, command=row['Command'], jobStatus='processed').set(jobs_processed)

                try:
                    pattern = r'(?P<queued>\d+)/(?P<wait>\d+)/(?P<failed>\d+)'
                    jobs_queued_wait_failed = row['Jobs (Queued/Wait/Failed),']  #trailing space automatically stripped
                    match = re.search(pattern, jobs_queued_wait_failed)
                    jobs_queued = int(match.group('queued'))
                    jobs_wait = int(match.group('wait'))
                    jobs_failed = int(match.group('failed'))
                except:
                    logging.warning(f'    Failed to parse jobs queued/wait/failed values for row "{row}"')
                else:
                    self.g_active_threads.labels(server=self.server_label, command=row['Command'], jobStatus='wait').set(jobs_wait)
                    self.g_active_threads.labels(server=self.server_label, command=row['Command'], jobStatus='failed').set(jobs_failed)
                    self.g_active_threads.labels(server=self.server_label, command=row['Command'], jobStatus='queued').set(jobs_queued)
                
                try:
                    jobs_selected = int(row['Jobs Selected'])   # Sometimes this value is "-", so don't assign a value for now if so
                except:
                    logging.warning(f'  Failed to parse "Jobs Selected" for row: {row}')
                else:
                    self.g_active_threads.labels(server=self.server_label, command=row['Command'], jobStatus='selected').set(jobs_selected)
                
            logging.info(f'  Metrics created for received notifications')
            
    def _parse_jobs_blocked(self, metrics_html):
        logging.info(f'  Parsing text for jobs blocked metrics')

        try:
            # breakpoint()
            pattern = r'Jobs blocked: <a href="/servlet/MonitorServlet\?servicename=Scheduler&actionpath=serverAction&Command=BlockedList">(?P<jobs_blocked>\d+)</a>'
            match = re.search(pattern, metrics_html)
            jobs_blocked = match.group('jobs_blocked')

        except:
            logging.warning(f'  Failed to match pattern for jobs blocked data. Not creating metric.')
        else:
            self.g_jobs_blocked.labels(server=self.server_label).set(jobs_blocked)      
            
            logging.info(f'  Metrics created for jobs blocked')

class SenderAppMetrics:
    """
    Functions to:
    * Initialize the class and define each metric that we're going to collect
    * Get the data from the source application metric page
    * Helper functions for formatting each type of metric to make code more readable
    """

    def __init__(self, metric_url, metric_server_label='unknown_merge_pacs_servername', metric_service_name='Merge PACS Process', \
        metric_prefix='merge_pacs_unk', metric_username='', metric_password='', metric_domain='healthpartners'):
        
        logging.info(f'Initializing the {self.__class__.__name__} metric data class')

        # The url where this service's metrics are available
        self.metric_url = metric_url

        # Define the label to use for {server=XXX} labels in each metric. Generally this should be the server's name
        self.server_label = metric_server_label
        
        # Define a service name for clarity in debugging
        self.service_name = metric_service_name

        # Define login information needed to get to the metrics
        self.metric_username = metric_username
        self.metric_password = metric_password
        self.metric_domain = metric_domain
 
        # What is the prefix string all these metrics will share? (Don't end in "_" -- one will be added)
        self.prefix = metric_prefix

        # Define the unique metrics to collect (labels will be added later)
        logging.info(f'Initializing metrics for {self.service_name}')
        self.g_database_connections = Gauge(f'{self.prefix}_database_connections', f'Database connections from the {self.service_name} service', ['server', 'dbConnectionStatus'])
        self.g_service_uptime = Gauge(f'{self.prefix}_server_uptime', f'Number of hours {self.service_name} has been running since last restart', ['server'])
        self.g_memory_current = Gauge(f'{self.prefix}_memory_current', f'Current memory utilization for various types from {self.service_name} service', ['server', 'memoryType'])
        self.g_memory_peak = Gauge(f'{self.prefix}_memory_peak', f'Peak memory utilization for various types from {self.service_name} service', ['server', 'memoryType'])

        self.g_job_queue = Gauge(f'{self.prefix}_job_queue', f'Jobs queued by status for the {self.service_name} service', ['server', 'status'])
        self.g_process_instance_stats = Gauge(f'{self.prefix}_instance_stats', f'Instances sent and failed since startup by the {self.service_name} service', ['server', 'status'])
        self.g_service_status = Gauge(f'{self.prefix}_service_status', f'Staus of the {self.service_name} service', ['server'])

    def fetch(self, http_request_timeout = 2.0):
        """ 
        Connect to the Merge PACS process's metrics page and parse results into Prometheus metrics
        """
        logging.info(f'Starting to collect metric data for {self.service_name} from {self.metric_url}')
        
        #clear old metrics
        self.g_database_connections.clear()
        self.g_service_uptime.clear()
        self.g_memory_current.clear()
        self.g_memory_peak.clear()
        self.g_job_queue.clear()
        self.g_process_instance_stats.clear()
        self.g_service_status.clear()
        
        # Get server status page data
        self.g_service_status.labels(server=self.server_label).set(0)
        try:
            r = requests.get(self.metric_url, timeout=http_request_timeout)
            
            # Raise an error if we have a 4XX or 5XX response
            r.raise_for_status()
        except requests.exceptions.Timeout:
            logging.error(f'Timed out getting metrics page {self.metric_url}!')
        except requests.exceptions.HTTPError as httperr:
            logging.error(f'HTTP error getting data from {self.metric_url}! Error: {httperr}')
        except requests.exceptions.RequestException as rex:
            # Some sort of catastrophic error. bail.
            logging.error(f'Failed getting metrics from {self.metric_url}! Error: {rex}')
        else:
            #set status to one if we can successfully able to get to page
            self.g_service_status.labels(server=self.server_label).set(1)

            ### Parse active and idle database connections
            # self._parse_database_connections(r.text)
            _parse_database_connections(database_connection_metric_obj=self.g_database_connections, server_label=self.server_label, metrics_html=r.text)

            ### Parse service uptime
            # self._parse_service_uptime(r.text)
            _parse_service_uptime(service_uptime_metric_obj=self.g_service_uptime, server_label=self.server_label, metrics_html=r.text)

            ### Parse memory utilization
            # self._parse_memory_utilization(r.text)
            _parse_memory_utilization(memory_current_metric_obj=self.g_memory_current, memory_peak_metric_obj=self.g_memory_peak, \
                server_label=self.server_label, metrics_html=r.text)

            ### Active threads 
            self._parse_job_queue_summary(r.text)

            ### Jobs blocked
            self._parse_send_summary(r.text)

        logging.info(f'Done fetching metrics for this polling interval for {self.service_name}')

    def _parse_job_queue_summary(self, metrics_html):
        logging.info(f'  Parsing text for sender job queue summary')
        try:
            pattern = r'Sender Job Queue Summary: New\((?P<new>\d+)\), Inprogress\((?P<in_progress>\d+)\), Error\((?P<error>\d+)\)'
            match = re.search(pattern, metrics_html)
            sender_job_queue_new = match.group('new')
            sender_job_queue_in_progress = match.group('in_progress')
            sender_job_queue_error = match.group('error')

        except:
            logging.warning(f'  Failed to match a pattern for the Sender Job Queue Summary data. Not creating metric.')
        else:
            self.g_job_queue.labels(server=self.server_label, status='new').set(sender_job_queue_new)
            self.g_job_queue.labels(server=self.server_label, status='in_progress').set(sender_job_queue_in_progress)
            self.g_job_queue.labels(server=self.server_label, status='error').set(sender_job_queue_error)

            logging.info(f'  Metrics created for sender job queue summary data')
            
    def _parse_send_summary(self, metrics_html):
        logging.info(f'  Parsing text for sender service summary stats')

        try:
            pattern = r'Send summary: <B>(?P<successful>\d+)</B> \(successful\) <B>(?P<failed>\d+)</B> \(failed\) instances'
            match = re.search(pattern, metrics_html)
            successful_instances = match.group('successful')
            failed_instances = match.group('failed')

        except:
            logging.warning(f'  Failed to match pattern for Send summary data. Not creating metric.')
        else:
            self.g_process_instance_stats.labels(server=self.server_label, status='successful').set(successful_instances)      
            self.g_process_instance_stats.labels(server=self.server_label, status='failed').set(failed_instances)      
            
            logging.info(f'  Metrics created for sender service Send summary')

### The three functions below to parse database connections (active and idle), service uptime, and memory utilization (peak and current) are used for 
### metrics as the information on each of the service pages is identical in layout for this information.
def _parse_database_connections(database_connection_metric_obj, server_label, metrics_html):
    try:
        logging.info(f'  Parsing text for database connection metrics')
        pattern = re.compile(r'Database connections: (?P<db_total>\d+) \((?P<db_idle>\d+) idle\)')
        match = re.search(pattern, metrics_html)
        db_active = int(match.group('db_total')) - int(match.group('db_idle'))
        db_idle = int(match.group('db_idle'))
    except Exception as err:
        # Failed to match patterns as expected
        logging.warning(f'Failed to match the pattern for database connections. Clearing previous value and leaving null. Error: {err}')
        database_connection_metric_obj.clear()
    else:
        # Populate Metric
        database_connection_metric_obj.labels(server=server_label, dbConnectionStatus='idle').set(db_idle)
        database_connection_metric_obj.labels(server=server_label, dbConnectionStatus='active').set(db_active)
        logging.info(f'  Metrics created for database connections')

def _parse_service_uptime(service_uptime_metric_obj, server_label, metrics_html):
    try:
        logging.info(f'  Parsing text for service uptime metric')
        pattern = re.compile(r'up time: ((?P<hours>\d+)h)?((?P<minutes>\d+)m)?(?P<seconds>\d+)\s?s')
        match = re.search(pattern, metrics_html)

        # There may be no "h" or "m" value if the service hasn't been running long enough
        try:
            hours = int(match.group('hours'))
        except:
            hours = 0                
        try:
            minutes = int(match.group('minutes'))
        except:
            minutes = 0
            
        seconds = int(match.group('seconds'))
        up_time_h = hours + (minutes / 60) + (seconds / (60 * 60))
    except Exception as err:
        # Failed to match patterns as expected
        logging.warning(f'Failed to match the pattern for server uptime. Clearing the current value and leaving null. Error: {err}')
        service_uptime_metric_obj.clear()
    else:
        # Populate metric
        service_uptime_metric_obj.labels(server=server_label).set(up_time_h)
        logging.info(f'  Metrics created for service uptime')

def _parse_memory_utilization(memory_current_metric_obj, memory_peak_metric_obj, server_label, metrics_html):
    try:
        logging.info(f'  Parsing text for memory utilization metrics')
        pattern = re.compile(r'Java (?P<java_current>\d+)MB\/(?P<java_peak>\d+)MB.*Native (?P<native_current>\d+)MB\/(?P<native_peak>\d+)MB.*Process Total (?P<process_current>\d+)MB\/(?P<process_peak>\d+)MB')
        match = re.search(pattern, metrics_html)
        java_current = match.group('java_current')
        java_peak = match.group('java_peak')
        native_current = match.group('native_current')
        native_peak = match.group('native_peak')
        process_current = match.group('process_current')
        process_peak = match.group('process_peak')
    except Exception as err:
        logging.warning(f'Failed to match the pattern for memory utilization. Clearing the current value and leaving null. Error: {err}')
        memory_current_metric_obj.clear()
    else:
        memory_current_metric_obj.labels(server=server_label, memoryType='java').set(java_current)
        memory_current_metric_obj.labels(server=server_label, memoryType='native').set(native_current)
        memory_current_metric_obj.labels(server=server_label, memoryType='process').set(process_current)
        memory_peak_metric_obj.labels(server=server_label, memoryType='java').set(java_peak)
        memory_peak_metric_obj.labels(server=server_label, memoryType='native').set(native_peak)
        memory_peak_metric_obj.labels(server=server_label, memoryType='process').set(process_peak)
        logging.info(f'  Metrics created for memory utilization')