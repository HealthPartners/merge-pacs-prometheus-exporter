from logging.handlers import DEFAULT_HTTP_LOGGING_PORT
import pandas as pd
import requests
from datetime import datetime
from datetime import timedelta
import re
from bs4 import BeautifulSoup
import time

# Definitions for the Notification Manager table of data
# Associate prometheus metric key to the appropriate column header in the data table. We're expecting a table like this:
# Format: 'Column Name in Data Table' : ['metric_name', 'metric_type', 'a helpful definition']
# example: 'Column Name' : ['metric_for_column_name', 'gauge', 'This metric measures something useful']
notification_manager_metrics = {
    'Jobs Constructed' :        ['merge_pacs_eanp_jobs_constructed',             'gauge', 'Number of jobs constructed recently(?)'],
    'Jobs being Constructed' :  ['merge_pacs_eanp_jobs_being_constructed',       'gauge', 'Number of jobs currently being constructed'],
    'Jobs Waiting for Locks' :  ['merge_pacs_eanp_jobs_jobs_waiting_for_locks',  'gauge', 'Jobs waiting for locks before they can be processed'],
    'Jobs Blocked' :            ['merge_pacs_eanp_jobs_blocked',                 'gauge', 'Jobs blocked that cannot currently begin processing'],
    'Jobs Dispatched' :         ['merge_pacs_eanp_jobs_dispatched',              'gauge', 'Jobs dispatched for processing'],
    'Dispatched Jobs Queued' :  ['merge_pacs_eanp_dispatched_jobs_queued',       'gauge', 'Jobs queues to be dispatched'],
    'Studies Locked' :          ['merge_pacs_eanp_studies_locked',               'gauge', 'Number of studies currently locked'],
    'Expected Instances' :      ['merge_pacs_eanp_expected_instances',           'gauge', 'Expected number of instances(?)'],
    'Expected Events' :         ['merge_pacs_eanp_expected_events',              'gauge', 'Expected number of events(?)'],
}

# Definitions for the Received Notifications table of data
# For this table, all data will be in a single metric and they will each have a separate tag to identify them
# Format: {Column Name' : 'additional_tags'}]
# example: 'Column Name' : 'notificationType=instance_notifications']
received_notifications_metrics = {
    'Instance Notifications'    : 'notificationType="instance_notifications"',
    'QC Notifications'          : 'notificationType="qc_notifications"',
    'Creates'                   : 'notificationType="creates"',
    'Deletes'                   : 'notificationType="deletes"',
    'Merges'                    : 'notificationType="merges"',
    'Moves'                     : 'notificationType="moves"',
    'Updates'                   : 'notificationType="updates"',
    'Replaces'                  : 'notificationType="replaces"',

}

# Definitions of other metrics, their help text and metric type. Generally these are all matched through pattern matching
# Format: {'metric_name': ['metric_type', 'a helpful definition', *'a string with additional tags']}
#   where the third argument is optional
other_metrics = {
    'merge_pacs_eanp_database_connections_active'   : ['gauge', 'Active database connections for the EA Notification processor service'],    #this will be calculated from data on the page
    'merge_pacs_eanp_database_connections_idle'     : ['gauge', 'Idle database connections for the EA Notification processor service'],
    'merge_pacs_eanp_java_memory_usage_current'     : ['gauge', 'EA Notification Processor java memory usage, current (MB)'],
    'merge_pacs_eanp_java_memory_usage_peak'        : ['counter', 'EA Notification Processor java memory usage, peak (MB)'],
    'merge_pacs_eanp_native_memory_usage_current'   : ['gauge', 'EA Notification Processor native memory usage, current (MB)'],
    'merge_pacs_eanp_native_memory_usage_peak'      : ['counter', 'EA Notification Processor native memory usage, peak (MB)'],
    'merge_pacs_eanp_active_studies'                : ['gauge', 'EA Notification Processor current active stuies'],
    'merge_pacs_eanp_images_processed'              : ['counter', 'EA Notification Processor images (objects) processed since process startup'],
    'merge_pacs_eanp_studies_processed'             : ['counter', 'EA Notification Processor studies processed since process startup'],
    'merge_pacs_eanp_studies_synced_last_hour'      : ['gauge', 'EA Notification Processor studies synced in last hour'],
    'merge_pacs_eanp_jms_sender_sessions'           : ['gauge', 'EA Notification Processor active JMS sender sessions'],
    'merge_pacs_eanp_jms_receiver_sessions'         : ['gauge', 'EA Notification Processor active JMS receiver sessions'],
    'merge_pacs_eanp_active_studies_idletime_max'   : ['gauge', 'Max idle time in the active studies'],
    'merge_pacs_eanp_active_studies_idletime_avg'   : ['gauge', 'Average idle time in the active studies'],

}

# servername = 'mergepacscnt'

# Output text in a list
output_list = []

# List of servers to check for status data
server_list = [
    'mergepacsprd',
    'mergepacscnt',
    'mergepacstest',
    'mergepacsrel',
]

# Default seconds before giving up on attempted connections by requests.get(). See https://docs.python-requests.org/en/latest/user/quickstart/#timeouts.
DEFAULT_HTTP_TIMEOUT = 2.0

def get_all_merge_pacs_metrics():
    results = main()
    return results

def get_notification_manager_metrics(url_text, column_names=[]):

    # Create dict of results with column_name -> value pairs
    results = {}

    try:
        df_list = pd.read_html(url_text, match=column_names[0], header=0) # this parses the table with the term matching the first column name we're expecting in to a list
    
    except:
        pass
    else:
        df = df_list[0]     # assume that there is only one table that matches (or at least that the FIRST table that matches is the one we want). 
                        # It should be the notification manager data
        for colname in column_names:    # Create a dict of colname -> value pairs. Assume there is only one data row that contains the relevant data.
            results[colname] = df[colname][0]

    finally:
        return results

def get_received_notifications_metrics(url_text, column_names=[]):
    # Arguments
    #   url_text - Text to parse (raw html)
    #   column_names[] - List of names of table header columns to look for in the raw html
    # 
    # Create dict of results with column_name -> value pairs
    results = {}
    try:
        df_list = pd.read_html(url_text, match=column_names[0], header=0) # this parses the table with the term matching the first column name we're expecting in to a list
    except:
        pass

    else:
        df = df_list[0]     # assume that there is only one table that matches (or at least that the FIRST table that matches is the one we want). 
                        # It should be the notification manager data
        for colname in column_names:
            results[colname] = df[colname][0]       # Create a dict of colname -> value pairs. Assume there is only one data row that contains the relevant data.
    finally:
        return results

def get_other_metrics(url_text):
    # Get other metrics through pattern matching. Returns a t dict of metric_name -> value
    # This function has to provide metric names that match defined function names in the larger program. See other_metrics[]

    metrics_dict = {}   # Dictionary to store results
    # Parse the database connection metrics
    # <DIV CLASS="SchedulerConnections">Database connections: 17 (11 idle),&nbsp;&nbsp;&nbsp; Server up time: 35h43m45s</DIV>
    s = re.search(r'connections: (?P<db_total>\d+) \((?P<db_idle>\d+)', url_text)
    if s:
        db_active = int(s.group('db_total')) - int(s.group('db_idle'))
        
        metrics_dict['merge_pacs_eanp_database_connections_active'] = db_active
        metrics_dict['merge_pacs_eanp_database_connections_idle'] = s.group('db_idle')
        

    # Parse the server uptime
    #<DIV CLASS="SchedulerConnections">Database connections: 17 (11 idle),&nbsp;&nbsp;&nbsp; Server up time: 35h43m45s</DIV>

    # Parse the memory usage
    s = re.search(r"Java (?P<java_current>\d+)MB\/(?P<java_peak>\d+)MB.*Native (?P<native_current>\d+)MB\/(?P<native_peak>\d+)MB", url_text)
    if s:
        metrics_dict['merge_pacs_eanp_java_memory_usage_current'] = s.group('java_current')
        metrics_dict['merge_pacs_eanp_java_memory_usage_peak'] = s.group('java_peak')
        metrics_dict['merge_pacs_eanp_native_memory_usage_current'] = s.group('native_current')
        metrics_dict['merge_pacs_eanp_native_memory_usage_peak'] = s.group('native_peak')

    # Parse active studies and number of images and studies processed since startup
    #<DIV CLASS="ActiveStudiesAndImages">Active studies:<B>31</B>,&nbsp;Processed since startup:<B>3790756</B> images / <B>51263</B> studies
    s = re.search(r'Active studies:<B>(?P<active_studies>\d+)<\/B>.*Processed since startup:<B>(?P<images_processed>\d+)<\/B> images \/ <B>(?P<studies_processed>\d+)<\/B> studies', url_text)
    if s:
        metrics_dict['merge_pacs_eanp_active_studies'] = s.group('active_studies')
        metrics_dict['merge_pacs_eanp_images_processed'] = s.group('images_processed')
        metrics_dict['merge_pacs_eanp_studies_processed'] = s.group('studies_processed')


    # Parse studies synced
    #<BR><B>Study Sync Manager:</B><BR>Number of studies synced in last hour: <B>293</B>...
    s = re.search(r'Number of studies synced in last hour: <B>(?P<studies_synced_last_hour>\d+)<\/B>', url_text)
    if s:
        metrics_dict['merge_pacs_eanp_studies_synced_last_hour'] = s.group('studies_synced_last_hour')

    

    # Parse JMS Sender and Receiver
    #<p><p><p><b>INTERNAL JMS Manager</b></p>Sender connection: 1<br>Receiver connection: 1<p/>...
    s = re.search(r'INTERNAL JMS Manager.*Sender connection: (?P<jms_sender_sessions>\d+)<br>Receiver connection: (?P<jms_receiver_sessions>\d+)', url_text)
    if s:
        metrics_dict['merge_pacs_eanp_jms_sender_sessions'] = s.group('jms_sender_sessions')
        metrics_dict['merge_pacs_eanp_jms_receiver_sessions'] = s.group('jms_receiver_sessions')
    
    #Parse active study Idle times
    try:
        Idletable = pd.read_html(url_text, match='Patient Name', header=0)
        Idle = Idletable[0]
        Idleclm = Idle[Idle.columns[10]]
        max_value = Idleclm.max()
        mean_value = Idleclm.mean()
        metrics_dict['merge_pacs_eanp_active_studies_idletime_max'] = max_value
        metrics_dict['merge_pacs_eanp_active_studies_idletime_avg'] = mean_value
    except:
        pass
    
    
    return metrics_dict


def main():
    # Dict of all column_name -> Value pairs for all metrics being collected
    notification_manager_values_list = {}
    received_notifications_values_list = {}
    other_metrics_values_list = {}
    output_list = []

    starttime = datetime.now()
    output_list.append(f'# Merge PACS metrics parsing output. Script started {datetime.ctime(starttime)}')

    for servername in server_list:
        
        # URL to get server status page for this server
        url = f'http://{servername}:11111/serverStatus'

        try:
            r = requests.get(url, timeout=3)
            #df_list = pd.read_html(r.text, match='Jobs Constructed', header=0) # this parses the table with the term 'Jobs' in it to a list
            #df = df_list[0]     # assume that there is only one table that matches (or at least that the FIRST table that matches is the one we want). 
                            # It should be the notification manager data
        except:
            pass

        else:
            # Parse the text to get the values for the Notification Manager table
            notification_manager_values_list[servername] = {}
            notification_manager_values_list[servername] = get_notification_manager_metrics(r.text, list(notification_manager_metrics.keys()))   # Pass in the text to parse and the column names we're expecting; add column names to list of metrics for this server

            # Parse the text to get values for the Received Notifications table
            received_notifications_values_list[servername] = {}
            received_notifications_values_list[servername] = get_received_notifications_metrics(r.text, list(received_notifications_metrics.keys()))   # Pass in the text to parse and the column names we're expecting; add column names to list of metrics for this server

            # Parse other metrics
            other_metrics_values_list[servername] = {}
            other_metrics_values_list[servername] = get_other_metrics(r.text)
    
    #
    # EA notification manager metrics
    #
    for colname in notification_manager_metrics:
        # Start with Notification Manager metrics
        # Extract the metric name, measurement type, and "help text" for this value from the definitions above
        metric_name, metric_type, help_text = notification_manager_metrics[colname] 
        #print(f'# HELP {metric_name} {help_text}')
        line = f'# HELP {metric_name} {help_text}'
        output_list.append(line)

        # print(f'# TYPE {metric_name} {metric_type}')
        line = f'# TYPE {metric_name} {metric_type}'
        output_list.append(line)
        
        for servername in notification_manager_values_list.keys():
            if colname in notification_manager_values_list[servername]:
                #print(f'{metric_name}{{server="{servername}"}} {notification_manager_values_list[servername][colname]}')
                line = f'{metric_name}{{server="{servername}"}} {notification_manager_values_list[servername][colname]}'
                output_list.append(line)
        #print(f'{metric_name}{{server="{servername}"}} {df[colname][0]}')  #assume there is only one data row that contains the relevant data
        #print()
        line = ''
        output_list.append(line)


    #
    # Received Notifications are all the same metric with the same help text
    #
    metric_name = 'merge_pacs_eanp_received_notifications'
    line = f'# HELP {metric_name} Notifications received from the EA in Merge PACS since last service restart'
    output_list.append(line)
    line = f'# TYPE {metric_name} counter'
    output_list.append(line)

    for colname in received_notifications_metrics:
        additional_tags = received_notifications_metrics[colname]
        if additional_tags:
            additional_tags = f',{additional_tags}' # add a leading comma if there are additional tags
        for servername in received_notifications_values_list.keys():
            if colname in received_notifications_values_list[servername]:
                #print(f'{metric_name}{{server="{servername}"{additional_tags}}} {received_notifications_values_list[servername][colname]}')
                line = f'{metric_name}{{server="{servername}"{additional_tags}}} {received_notifications_values_list[servername][colname]}'
                output_list.append(line)

    line = ''
    output_list.append(line)


    #
    # Get other metrics, mainly by pattern matches
    #
    for metric_name in other_metrics:
        # For this metric, get the metric type, help text, and any supplied (optional) string of additional tags
        metric_type, metric_help, *metric_tag_string = other_metrics[metric_name]

        # Print the HELP for this metric
        line = f'# HELP {metric_name} {metric_help}'
        output_list.append(line)

        # Print the TYPE for this metric
        line = f'# TYPE {metric_name} {metric_type}'
        output_list.append(line)

        #format for data: other_metrics_values_list[server name][metric name]
        for servername in other_metrics_values_list.keys():
            if metric_name in other_metrics_values_list[servername]:
                if metric_tag_string:
                    line = f'{metric_name}{{server="{servername}",{metric_tag_string[0]}}} {other_metrics_values_list[servername][metric_name]}'
                else:
                    line = f'{metric_name}{{server="{servername}"}} {other_metrics_values_list[servername][metric_name]}'
                output_list.append(line)

        output_list.append('')        # Blank line at the end of each metric

    # List of servers to check for status data for port 11109
    server_list_2 = [
        'mergepacsprd',
        'mergepacscnt',
        'mergepacstest',
        'mergepacsrel',
    ]


    output_list.append(f'# HELP merge_pacs_cms_active_users active users on the system')
    output_list.append(f'# TYPE merge_pacs_cms_active_users gauge')
    for servername in server_list_2:
        url = f'http://{servername}:11109/serverStatus'
        try:
            r = requests.get(url)
        except:
            pass
        else:
            #Active users
            pattern = r'Active pipelines:<B> (?P<active_users>\d+)'
            get = re.search(pattern, r.text)
            if get:
                Data = get.group('active_users')
                output_list.append(f'merge_pacs_cms_active_users{{server="{servername}"}} {Data}')
    output_list.append('')

    
    # List of servers to check for status data For port 11108
    server_list_3 = [
        'mergepacsprd',
        'mergepacscnt',
        'mergepacstest',
        'mergepacsrel',
    ]

    for servername in server_list_3:
        url = f'http://{servername}:11108/serverStatus'

        try:
            r = requests.get(url)
        except:
            pass
        else:
            
            #Active and Idle DB connections
            try:
                s = re.search(r'connections: (?P<db_total>\d+) \((?P<db_idle>\d+)', r.text)
                db_active = int(s.group('db_total')) - int(s.group('db_idle'))
                active = db_active
                idle = s.group('db_idle')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_wss_database_connections_active active database connections from worklist server port 11108')
                output_list.append(f'# TYPE merge_pacs_wss_database_connections_active gauge')
                output_list.append(f'merge_pacs_wss_database_connections_active{{server="{servername}"}} {active}')
                output_list.append(f'# HELP merge_pacs_wss_database_connections_idle idle database connections from worklist server port 11108')
                output_list.append(f'# TYPE merge_pacs_wss_database_connections_idle gauge')
                output_list.append(f'merge_pacs_wss_database_connections_idle{{server="{servername}"}} {idle}')
                output_list.append('')
            #server Up time
            try:
                try:
                    u = re.search(r'up time: (?P<seconds>\d+)s', r.text)
                    seconds = int(u.group('seconds'))
                    up_time = (total_seconds / 3600)
                except:
                    pass

                try:
                    u = re.search(r'up time: (?P<minutes>\d+)m(?P<seconds>\d+)s', r.text)
                    minutes = int(u.group('minutes'))
                    seconds = int(u.group('seconds'))
                    total_seconds = ((minutes * 60) + seconds)
                    up_time = (total_seconds / 3600)
                except:
                    pass

                try:
                    u = re.search(r'up time: (?P<hours>\d+)h(?P<minutes>\d+)m(?P<seconds>\d+)s', r.text)
                    hours = int(u.group('hours'))
                    minutes = int(u.group('minutes'))
                    seconds = int(u.group('seconds'))
                    total_seconds = ((minutes * 60) + seconds)
                    total_hours = (total_seconds / 3600)
                    up_time = hours + total_hours
                except:
                    pass
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_wss_server_uptime server continously running since how many hours from worklist server port 11108')
                output_list.append(f'# TYPE merge_pacs_wss_server_uptime gauge')
                output_list.append(f'merge_pacs_wss_server_uptime{{server="{servername}"}} {up_time}')
                output_list.append('')

            #memory usage
            try:
                u = re.search(r'Java (?P<java_current>\d+)MB\/(?P<java_peak>\d+)MB.*Native (?P<native_current>\d+)MB\/(?P<native_peak>\d+)MB.*Process Total (?P<process_current>\d+)MB\/(?P<process_peak>\d+)MB', r.text)
                java_current = u.group('java_current')
                java_peak = u.group('java_peak')
                native_current = u.group('native_current')
                native_peak = u.group('native_peak')
                process_current = u.group('process_current')
                process_peak = u.group('process_peak')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_wss_memory_usage server usage of memory for various types from worklist server port 11108')
                output_list.append(f'# TYPE merge_pacs_wss_memory_usage counter')
                output_list.append(f'merge_pacs_wss_memory_usage{{server="{servername}",memoryType="java_current"}} {java_current}')
                output_list.append(f'merge_pacs_wss_memory_usage{{server="{servername}",memoryType="java_peak"}} {java_peak}')
                output_list.append(f'merge_pacs_wss_memory_usage{{server="{servername}",memoryType="native_current"}} {native_current}')
                output_list.append(f'merge_pacs_wss_memory_usage{{server="{servername}",memoryType="native_peak"}} {native_peak}')
                output_list.append(f'merge_pacs_wss_memory_usage{{server="{servername}",memoryType="process_current"}} {process_current}')
                output_list.append(f'merge_pacs_wss_memory_usage{{server="{servername}",memoryType="process_peak"}} {process_peak}')
                output_list.append('')
            #connected clients and Active worklist
            try:
                u = re.search(r'clients: <B>(?P<connected_clients>\d+)</B><br>Active worklists: <B>(?P<loaded>\d+) loaded, (?P<loading>\d+) loading, (?P<selecting>\d+) selecting, (?P<waiting>\d+) ', r.text)
                connected_clients = u.group('connected_clients')
                loaded = u.group('loaded')
                loading = u.group('loading')
                selecting = u.group('selecting')
                waiting = u.group('waiting')
            except:
                pass
            else:               
                #Connected Clients print
                output_list.append(f'# HELP merge_pacs_wss_connected_clients number of connected clients from worklist server port 11108')
                output_list.append(f'# TYPE merge_pacs_wss_connected_clients gauge')
                output_list.append(f'merge_pacs_wss_connected_clients{{server="{servername}"}} {connected_clients}')
                output_list.append('')
                #Active Worklist print
                output_list.append(f'# HELP merge_pacs_wss_active_worklists various active worklists from worklist server port 11108')
                output_list.append(f'# TYPE merge_pacs_wss_active_worklists counter')
                output_list.append(f'merge_pacs_wss_active_worklists{{server="{servername}",worklisType="loaded"}} {loaded}')
                output_list.append(f'merge_pacs_wss_active_worklists{{server="{servername}",worklisType="loading"}} {loading}')
                output_list.append(f'merge_pacs_wss_active_worklists{{server="{servername}",worklisType="selecting"}} {selecting}')
                output_list.append(f'merge_pacs_wss_active_worklists{{server="{servername}",worklisType="waiting"}} {waiting}')
                output_list.append('')
            #exam cache
            try:
                u = re.search(r'Loaded exams: (?P<loaded_exams>\d+) .*. Stale exams: (?P<stale_exams>\d+). Exam loads: (?P<exam_loads>\d+) ', r.text)
                loaded_exams = u.group('loaded_exams')
                stale_exams = u.group('stale_exams')
                exam_loads = u.group('exam_loads')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_wss_exam_cache number of cached exams from worklist server port 11108')
                output_list.append(f'# TYPE merge_pacs_wss_exam_cache counter')
                output_list.append(f'merge_pacs_wss_exam_cache{{server="{servername}",examcachetype="loaded"}} {loaded_exams}')
                output_list.append(f'merge_pacs_wss_exam_cache{{server="{servername}",examcachetype="stale"}} {stale_exams}')
                output_list.append(f'merge_pacs_wss_exam_cache{{server="{servername}",examcachetype="loads"}} {exam_loads}')
                output_list.append('')

            #pending jobs
            try:
                u = re.search(r'Pending jobs</a> - Exam requests: (?P<exam_requests>\d+). Patient updates: (?P<patient_updates>\d+). Order updates: (?P<order_updates>\d+). Study updates: (?P<study_updates>\d+). Status updates: (?P<status_updates>\d+). Instance count updates: (?P<instance_count_updates>\d+). Custom tag updates: (?P<custom_tag_updates>\d+)', r.text)
                exam_requests = u.group('exam_requests')
                patient_updates = u.group('patient_updates')
                order_updates = u.group('order_updates')
                study_updates = u.group('study_updates')
                status_updates = u.group('status_updates')
                instance_count_updates = u.group('instance_count_updates')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_wss_pending_jobs various pending jobs from worklist server port 11108')
                output_list.append(f'# TYPE merge_pacs_wss_pending_jobs counter')
                output_list.append(f'merge_pacs_wss_pending_jobs{{server="{servername}",pendingjobsType="exam_requests"}} {exam_requests}')
                output_list.append(f'merge_pacs_wss_pending_jobs{{server="{servername}",pendingjobsType="patient_updates"}} {patient_updates}')
                output_list.append(f'merge_pacs_wss_pending_jobs{{server="{servername}",pendingjobsType="order_updates"}} {order_updates}')
                output_list.append(f'merge_pacs_wss_pending_jobs{{server="{servername}",pendingjobsType="study_updates"}} {study_updates}')
                output_list.append(f'merge_pacs_wss_pending_jobs{{server="{servername}",pendingjobsType="status_updates"}} {status_updates}')
                output_list.append('')

    # List of servers to check for status data For port 11098 which is Scheduler service
    server_list_4 = [
        'mergepacsprd',
        'mergepacscnt',
        'mergepacstest',
        'mergepacsrel',
    ]

    for servername in server_list_4:
        url = f'http://{servername}:11098/serverStatus'
        try:
            r = requests.get(url)
            
            
        except:
            pass
        else:
            
            #Active and Idle DB connections
            try:
                s = re.search(r'connections: (?P<db_total>\d+) \((?P<db_idle>\d+)', r.text)
                db_active = int(s.group('db_total')) - int(s.group('db_idle'))
                active = db_active
                idle = s.group('db_idle')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_ss_database_connections_active active database connections from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_database_connections_active gauge')
                output_list.append(f'merge_pacs_ss_database_connections_active{{server="{servername}"}} {active}')
                output_list.append(f'# HELP merge_pacs_ss_database_connections_idle idle database connections from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_database_connections_idle gauge')
                output_list.append(f'merge_pacs_ss_database_connections_idle{{server="{servername}"}} {idle}')
                output_list.append('')
            #server Up time
            try:
                try:
                    u = re.search(r'up time: (?P<seconds>\d+)s', r.text)
                    seconds = int(u.group('seconds'))
                    up_time = (total_seconds / 3600)
                except:
                    pass

                try:
                    u = re.search(r'up time: (?P<minutes>\d+)m(?P<seconds>\d+)s', r.text)
                    minutes = int(u.group('minutes'))
                    seconds = int(u.group('seconds'))
                    total_seconds = ((minutes * 60) + seconds)
                    up_time = (total_seconds / 3600)
                except:
                    pass

                try:
                    u = re.search(r'up time: (?P<hours>\d+)h(?P<minutes>\d+)m(?P<seconds>\d+)s', r.text)
                    hours = int(u.group('hours'))
                    minutes = int(u.group('minutes'))
                    seconds = int(u.group('seconds'))
                    total_seconds = ((minutes * 60) + seconds)
                    total_hours = (total_seconds / 3600)
                    up_time = hours + total_hours
                except:
                    pass
            except:
                pass
            else:  
                output_list.append(f'# HELP merge_pacs_ss_server_uptime server continously running since how many hours from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_server_uptime gauge')
                output_list.append(f'merge_pacs_ss_database_server_uptime{{server="{servername}"}} {up_time}')
                output_list.append('')

            #memory usage
            try:
                u = re.search(r'Java (?P<java_current>\d+)MB\/(?P<java_peak>\d+)MB.*Native (?P<native_current>\d+)MB\/(?P<native_peak>\d+)MB.*Process Total (?P<process_current>\d+)MB\/(?P<process_peak>\d+)MB', r.text)
                java_current = u.group('java_current')
                java_peak = u.group('java_peak')
                native_current = u.group('native_current')
                native_peak = u.group('native_peak')
                process_current = u.group('process_current')
                process_peak = u.group('process_peak')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_ss_memory_usage server usage of memory for various types from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_memory_usage counter')
                output_list.append(f'merge_pacs_ss_memory_usage{{server="{servername}",memoryType="java_current"}} {java_current}')
                output_list.append(f'merge_pacs_ss_memory_usage{{server="{servername}",memoryType="java_peak"}} {java_peak}')
                output_list.append(f'merge_pacs_ss_memory_usage{{server="{servername}",memoryType="native_current"}} {native_current}')
                output_list.append(f'merge_pacs_ss_memory_usage{{server="{servername}",memoryType="native_peak"}} {native_peak}')
                output_list.append(f'merge_pacs_ss_memory_usage{{server="{servername}",memoryType="process_current"}} {process_current}')
                output_list.append(f'merge_pacs_ss_memory_usage{{server="{servername}",memoryType="process_peak"}} {process_peak}')
                output_list.append('')
            
            #Validate
            try:
                u = re.search(r'Validate</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                Validate_Processed = u.group('a')
                Validate_Queued = u.group('b')
                Validate_Wait = u.group('c')
                Validate_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_validate from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_validate counter')
                output_list.append(f'merge_pacs_ss_validate{{server="{servername}",ActiveThreadType="processed"}} {Validate_Processed}')
                output_list.append(f'merge_pacs_ss_validate{{server="{servername}",ActiveThreadType="queued"}} {Validate_Queued}')
                output_list.append(f'merge_pacs_ss_validate{{server="{servername}",ActiveThreadType="wait"}} {Validate_Wait}')
                output_list.append(f'merge_pacs_ss_validate{{server="{servername}",ActiveThreadType="failed"}} {Validate_Failed}')
                output_list.append('')
            
            #Update
            try:
                u = re.search(r'Update</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                Update_Processed = u.group('a')
                Update_Queued = u.group('b')
                Update_Wait = u.group('c')
                Update_Failed = u.group('d')
            except:
                pass
            else:
                #Print
                output_list.append(f'# HELP merge_pacs_ss_Update from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_Update counter')
                output_list.append(f'merge_pacs_ss_Update{{server="{servername}",ActiveThreadType="processed"}} {Update_Processed}')
                output_list.append(f'merge_pacs_ss_Update{{server="{servername}",ActiveThreadType="queued"}} {Update_Queued}')
                output_list.append(f'merge_pacs_ss_Update{{server="{servername}",ActiveThreadType="wait"}} {Update_Wait}')
                output_list.append(f'merge_pacs_ss_Update{{server="{servername}",ActiveThreadType="failed"}} {Update_Failed}')
                output_list.append('')
            

            #StudyRetrieve
            try:
                u = re.search(r'StudyRetrieve</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                StudyRetrieve_Processed = u.group('a')
                StudyRetrieve_Queued = u.group('b')
                StudyRetrieve_Wait = u.group('c')
                StudyRetrieve_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_study_retrieve from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_study_retrieve counter')
                output_list.append(f'merge_pacs_ss_study_retrieve{{server="{servername}",ActiveThreadType="processed"}} {StudyRetrieve_Processed}')
                output_list.append(f'merge_pacs_ss_study_retrieve{{server="{servername}",ActiveThreadType="queued"}} {StudyRetrieve_Queued}')
                output_list.append(f'merge_pacs_ss_study_retrieve{{server="{servername}",ActiveThreadType="wait"}} {StudyRetrieve_Wait}')
                output_list.append(f'merge_pacs_ss_study_retrieve{{server="{servername}",ActiveThreadType="failed"}} {StudyRetrieve_Failed}')
                output_list.append('')

            #SetStatus
            try:
                u = re.search(r'SetStatus</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                SetStatus_Processed = u.group('a')
                SetStatus_Queued = u.group('b')
                SetStatus_Wait = u.group('c')
                SetStatus_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_SetStatus from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_SetStatus counter')
                output_list.append(f'merge_pacs_ss_SetStatus{{server="{servername}",ActiveThreadType="processed"}} {SetStatus_Processed}')
                output_list.append(f'merge_pacs_ss_SetStatus{{server="{servername}",ActiveThreadType="queued"}} {SetStatus_Queued}')
                output_list.append(f'merge_pacs_ss_SetStatus{{server="{servername}",ActiveThreadType="wait"}} {SetStatus_Wait}')
                output_list.append(f'merge_pacs_ss_SetStatus{{server="{servername}",ActiveThreadType="failed"}} {SetStatus_Failed}')
                output_list.append('')

            #QCFunctionMove
            try:
                u = re.search(r'QCFunctionMove</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                QCFunctionMove_Processed = u.group('a')
                QCFunctionMove_Queued = u.group('b')
                QCFunctionMove_Wait = u.group('c')
                QCFunctionMove_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_QCFunctionMove from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_QCFunctionMove counter')
                output_list.append(f'merge_pacs_ss_QCFunctionMove{{server="{servername}",ActiveThreadType="processed"}} {QCFunctionMove_Processed}')
                output_list.append(f'merge_pacs_ss_QCFunctionMove{{server="{servername}",ActiveThreadType="queued"}} {QCFunctionMove_Queued}')
                output_list.append(f'merge_pacs_ss_QCFunctionMove{{server="{servername}",ActiveThreadType="wait"}} {QCFunctionMove_Wait}')
                output_list.append(f'merge_pacs_ss_QCFunctionMove{{server="{servername}",ActiveThreadType="failed"}} {QCFunctionMove_Failed}')
                output_list.append('')
            
            #QCFunctionMergeStudyOriginalStudyUID
            try:
                u = re.search(r'QCFunctionMergeStudyOriginalStudyUID</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                QCFunctionMergeStudyOriginalStudyUID_Processed = u.group('a')
                QCFunctionMergeStudyOriginalStudyUID_Queued = u.group('b')
                QCFunctionMergeStudyOriginalStudyUID_Wait = u.group('c')
                QCFunctionMergeStudyOriginalStudyUID_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_QCFunctionMergeStudyOriginalStudyUID from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_QCFunctionMergeStudyOriginalStudyUID counter')
                output_list.append(f'merge_pacs_ss_QCFunctionMergeStudyOriginalStudyUID{{server="{servername}",ActiveThreadType="processed"}} {QCFunctionMergeStudyOriginalStudyUID_Processed}')
                output_list.append(f'merge_pacs_ss_QCFunctionMergeStudyOriginalStudyUID{{server="{servername}",ActiveThreadType="queued"}} {QCFunctionMergeStudyOriginalStudyUID_Queued}')
                output_list.append(f'merge_pacs_ss_QCFunctionMergeStudyOriginalStudyUID{{server="{servername}",ActiveThreadType="wait"}} {QCFunctionMergeStudyOriginalStudyUID_Wait}')
                output_list.append(f'merge_pacs_ss_QCFunctionMergeStudyOriginalStudyUID{{server="{servername}",ActiveThreadType="failed"}} {QCFunctionMergeStudyOriginalStudyUID_Failed}')
                output_list.append('')

            #QCFunctionMerge
            try:
                u = re.search(r'QCFunctionMerge</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                QCFunctionMerge_Processed = u.group('a')
                QCFunctionMerge_Queued = u.group('b')
                QCFunctionMerge_Wait = u.group('c')
                QCFunctionMerge_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_QCFunctionMerge from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_QCFunctionMerge counter')
                output_list.append(f'merge_pacs_ss_QCFunctionMerge{{server="{servername}",ActiveThreadType="processed"}} {QCFunctionMerge_Processed}')
                output_list.append(f'merge_pacs_ss_QCFunctionMerge{{server="{servername}",ActiveThreadType="queued"}} {QCFunctionMerge_Queued}')
                output_list.append(f'merge_pacs_ss_QCFunctionMerge{{server="{servername}",ActiveThreadType="wait"}} {QCFunctionMerge_Wait}')
                output_list.append(f'merge_pacs_ss_QCFunctionMerge{{server="{servername}",ActiveThreadType="failed"}} {QCFunctionMerge_Failed}')
                output_list.append('')
            
            #QCFunctionDelete
            try:
                u = re.search(r'QCFunctionDelete</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                QCFunctionDelete_Processed = u.group('a')
                QCFunctionDelete_Queued = u.group('b')
                QCFunctionDelete_Wait = u.group('c')
                QCFunctionDelete_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_QCFunctionDelete from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_QCFunctionDelete counter')
                output_list.append(f'merge_pacs_ss_QCFunctionDelete{{server="{servername}",ActiveThreadType="processed"}} {QCFunctionDelete_Processed}')
                output_list.append(f'merge_pacs_ss_QCFunctionDelete{{server="{servername}",ActiveThreadType="queued"}} {QCFunctionDelete_Queued}')
                output_list.append(f'merge_pacs_ss_QCFunctionDelete{{server="{servername}",ActiveThreadType="wait"}} {QCFunctionDelete_Wait}')
                output_list.append(f'merge_pacs_ss_QCFunctionDelete{{server="{servername}",ActiveThreadType="failed"}} {QCFunctionDelete_Failed}')
                output_list.append('')

            #PeriodicCleanupDB
            try:
                u = re.search(r'PeriodicCleanupDB</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                PeriodicCleanupDB_Processed = u.group('a')
                PeriodicCleanupDB_Queued = u.group('b')
                PeriodicCleanupDB_Wait = u.group('c')
                PeriodicCleanupDB_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_PeriodicCleanupDB from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_PeriodicCleanupDB counter')
                output_list.append(f'merge_pacs_ss_PeriodicCleanupDB{{server="{servername}",ActiveThreadType="processed"}} {PeriodicCleanupDB_Processed}')
                output_list.append(f'merge_pacs_ss_PeriodicCleanupDB{{server="{servername}",ActiveThreadType="queued"}} {PeriodicCleanupDB_Queued}')
                output_list.append(f'merge_pacs_ss_PeriodicCleanupDB{{server="{servername}",ActiveThreadType="wait"}} {PeriodicCleanupDB_Wait}')
                output_list.append(f'merge_pacs_ss_PeriodicCleanupDB{{server="{servername}",ActiveThreadType="failed"}} {PeriodicCleanupDB_Failed}')
                output_list.append('')
            
            #PACSStatsJob
            try:
                u = re.search(r'PACSStatsJob</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                PACSStatsJob_Processed = u.group('a')
                PACSStatsJob_Queued = u.group('b')
                PACSStatsJob_Wait = u.group('c')
                PACSStatsJob_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_PACSStatsJob from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_PACSStatsJob counter')
                output_list.append(f'merge_pacs_ss_PACSStatsJob{{server="{servername}",ActiveThreadType="processed"}} {PACSStatsJob_Processed}')
                output_list.append(f'merge_pacs_ss_PACSStatsJob{{server="{servername}",ActiveThreadType="queued"}} {PACSStatsJob_Queued}')
                output_list.append(f'merge_pacs_ss_PACSStatsJob{{server="{servername}",ActiveThreadType="wait"}} {PACSStatsJob_Wait}')
                output_list.append(f'merge_pacs_ss_PACSStatsJob{{server="{servername}",ActiveThreadType="failed"}} {PACSStatsJob_Failed}')
                output_list.append('')
            
            #NightlySyncToolInvoker
            try:
                u = re.search(r'NightlySyncToolInvoker</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                NightlySyncToolInvoker_Processed = u.group('a')
                NightlySyncToolInvoker_Queued = u.group('b')
                NightlySyncToolInvoker_Wait = u.group('c')
                NightlySyncToolInvoker_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_NightlySyncToolInvoker from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_NightlySyncToolInvoker counter')
                output_list.append(f'merge_pacs_ss_NightlySyncToolInvoker{{server="{servername}",ActiveThreadType="processed"}} {NightlySyncToolInvoker_Processed}')
                output_list.append(f'merge_pacs_ss_NightlySyncToolInvoker{{server="{servername}",ActiveThreadType="queued"}} {NightlySyncToolInvoker_Queued}')
                output_list.append(f'merge_pacs_ss_NightlySyncToolInvoker{{server="{servername}",ActiveThreadType="wait"}} {NightlySyncToolInvoker_Wait}')
                output_list.append(f'merge_pacs_ss_NightlySyncToolInvoker{{server="{servername}",ActiveThreadType="failed"}} {NightlySyncToolInvoker_Failed}')
                output_list.append('')

            #NightlySyncTool
            try:
                u = re.search(r'NightlySyncTool</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                NightlySyncTool_Processed = u.group('a')
                NightlySyncTool_Queued = u.group('b')
                NightlySyncTool_Wait = u.group('c')
                NightlySyncTool_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_NightlySyncTool from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_NightlySyncTool counter')
                output_list.append(f'merge_pacs_ss_NightlySyncTool{{server="{servername}",ActiveThreadType="processed"}} {NightlySyncTool_Processed}')
                output_list.append(f'merge_pacs_ss_NightlySyncTool{{server="{servername}",ActiveThreadType="queued"}} {NightlySyncTool_Queued}')
                output_list.append(f'merge_pacs_ss_NightlySyncTool{{server="{servername}",ActiveThreadType="wait"}} {NightlySyncTool_Wait}')
                output_list.append(f'merge_pacs_ss_NightlySyncTool{{server="{servername}",ActiveThreadType="failed"}} {NightlySyncTool_Failed}')
                output_list.append('')

            #MiscellaneousJobs
            try:
                u = re.search(r'MiscellaneousJobs</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                MiscellaneousJobs_Processed = u.group('a')
                MiscellaneousJobs_Queued = u.group('b')
                MiscellaneousJobs_Wait = u.group('c')
                MiscellaneousJobs_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_MiscellaneousJobs from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_MiscellaneousJobs counter')
                output_list.append(f'merge_pacs_ss_MiscellaneousJobs{{server="{servername}",ActiveThreadType="processed"}} {MiscellaneousJobs_Processed}')
                output_list.append(f'merge_pacs_ss_MiscellaneousJobs{{server="{servername}",ActiveThreadType="queued"}} {MiscellaneousJobs_Queued}')
                output_list.append(f'merge_pacs_ss_MiscellaneousJobs{{server="{servername}",ActiveThreadType="wait"}} {MiscellaneousJobs_Wait}')
                output_list.append(f'merge_pacs_ss_MiscellaneousJobs{{server="{servername}",ActiveThreadType="failed"}} {MiscellaneousJobs_Failed}')
                output_list.append('')
            
            #Merge
            try:
                u = re.search(r'<TD>Merge</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                Merge_Processed = u.group('a')
                Merge_Queued = u.group('b')
                Merge_Wait = u.group('c')
                Merge_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_Merge from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_Merge counter')
                output_list.append(f'merge_pacs_ss_Merge{{server="{servername}",ActiveThreadType="processed"}} {Merge_Processed}')
                output_list.append(f'merge_pacs_ss_Merge{{server="{servername}",ActiveThreadType="queued"}} {Merge_Queued}')
                output_list.append(f'merge_pacs_ss_Merge{{server="{servername}",ActiveThreadType="wait"}} {Merge_Wait}')
                output_list.append(f'merge_pacs_ss_Merge{{server="{servername}",ActiveThreadType="failed"}} {Merge_Failed}')
                output_list.append('')

            #ImportLogExtractorInvoker
            try:
                u = re.search(r'ImportLogExtractorInvoker</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                ImportLogExtractorInvoker_Processed = u.group('a')
                ImportLogExtractorInvoker_Queued = u.group('b')
                ImportLogExtractorInvoker_Wait = u.group('c')
                ImportLogExtractorInvoker_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP ImportLogExtractorInvoker_pacs_ss_ImportLogExtractorInvoker from Scheduler service port 11098')
                output_list.append(f'# TYPE ImportLogExtractorInvoker_pacs_ss_ImportLogExtractorInvoker counter')
                output_list.append(f'merge_pacs_ss_ImportLogExtractorInvoker{{server="{servername}",ActiveThreadType="processed"}} {ImportLogExtractorInvoker_Processed}')
                output_list.append(f'merge_pacs_ss_ImportLogExtractorInvoker{{server="{servername}",ActiveThreadType="queued"}} {ImportLogExtractorInvoker_Queued}')
                output_list.append(f'merge_pacs_ss_ImportLogExtractorInvoker{{server="{servername}",ActiveThreadType="wait"}} {ImportLogExtractorInvoker_Wait}')
                output_list.append(f'merge_pacs_ss_ImportLogExtractorInvoker{{server="{servername}",ActiveThreadType="failed"}} {ImportLogExtractorInvoker_Failed}')
                output_list.append('')

            #DataStorageCacheCleanup
            try:
                u = re.search(r'DataStorageCacheCleanup</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                DataStorageCacheCleanup_Processed = u.group('a')
                DataStorageCacheCleanup_Queued = u.group('b')
                DataStorageCacheCleanup_Wait = u.group('c')
                DataStorageCacheCleanup_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_DataStorageCacheCleanup from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_DataStorageCacheCleanup counter')
                output_list.append(f'merge_pacs_ss_DataStorageCacheCleanup{{server="{servername}",ActiveThreadType="processed"}} {DataStorageCacheCleanup_Processed}')
                output_list.append(f'merge_pacs_ss_DataStorageCacheCleanup{{server="{servername}",ActiveThreadType="queued"}} {DataStorageCacheCleanup_Queued}')
                output_list.append(f'merge_pacs_ss_DataStorageCacheCleanup{{server="{servername}",ActiveThreadType="wait"}} {DataStorageCacheCleanup_Wait}')
                output_list.append(f'merge_pacs_ss_DataStorageCacheCleanup{{server="{servername}",ActiveThreadType="failed"}} {DataStorageCacheCleanup_Failed}')
                output_list.append('')
            
            #CleanupFolders
            try:
                u = re.search(r'CleanupFolders</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                CleanupFolders_Processed = u.group('a')
                CleanupFolders_Queued = u.group('b')
                CleanupFolders_Wait = u.group('c')
                CleanupFolders_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_CleanupFolders from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_CleanupFolders counter')
                output_list.append(f'merge_pacs_ss_CleanupFolders{{server="{servername}",ActiveThreadType="processed"}} {CleanupFolders_Processed}')
                output_list.append(f'merge_pacs_ss_CleanupFolders{{server="{servername}",ActiveThreadType="queued"}} {CleanupFolders_Queued}')
                output_list.append(f'merge_pacs_ss_CleanupFolders{{server="{servername}",ActiveThreadType="wait"}} {CleanupFolders_Wait}')
                output_list.append(f'merge_pacs_ss_CleanupFolders{{server="{servername}",ActiveThreadType="failed"}} {CleanupFolders_Failed}')
                output_list.append('')
            
            #CheckResources
            try:
                u = re.search(r'CheckResources</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                CheckResources_Processed = u.group('a')
                CheckResources_Queued = u.group('b')
                CheckResources_Wait = u.group('c')
                CheckResources_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_CheckResources from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_CheckResources counter')
                output_list.append(f'merge_pacs_ss_CheckResources{{server="{servername}",ActiveThreadType="processed"}} {CheckResources_Processed}')
                output_list.append(f'merge_pacs_ss_CheckResources{{server="{servername}",ActiveThreadType="queued"}} {CheckResources_Queued}')
                output_list.append(f'merge_pacs_ss_CheckResources{{server="{servername}",ActiveThreadType="wait"}} {CheckResources_Wait}')
                output_list.append(f'merge_pacs_ss_CheckResources{{server="{servername}",ActiveThreadType="failed"}} {CheckResources_Failed}')
                output_list.append('')

            #AuditExtractorInvoker
            try:
                u = re.search(r'AuditExtractorInvoker</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                AuditExtractorInvoker_Processed = u.group('a')
                AuditExtractorInvoker_Queued = u.group('b')
                AuditExtractorInvoker_Wait = u.group('c')
                AuditExtractorInvoker_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_AuditExtractorInvoker from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_AuditExtractorInvoker counter')
                output_list.append(f'merge_pacs_ss_AuditExtractorInvoker{{server="{servername}",ActiveThreadType="processed"}} {AuditExtractorInvoker_Processed}')
                output_list.append(f'merge_pacs_ss_AuditExtractorInvoker{{server="{servername}",ActiveThreadType="queued"}} {AuditExtractorInvoker_Queued}')
                output_list.append(f'merge_pacs_ss_AuditExtractorInvoker{{server="{servername}",ActiveThreadType="wait"}} {AuditExtractorInvoker_Wait}')
                output_list.append(f'merge_pacs_ss_AuditExtractorInvoker{{server="{servername}",ActiveThreadType="failed"}} {AuditExtractorInvoker_Failed}')
                output_list.append('')

            #AnetCommunicatorEntries
            try:
                u = re.search(r'AnetCommunicatorEntries</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                AnetCommunicatorEntries_Processed = u.group('a')
                AnetCommunicatorEntries_Queued = u.group('b')
                AnetCommunicatorEntries_Wait = u.group('c')
                AnetCommunicatorEntries_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_AnetCommunicatorEntries from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_AnetCommunicatorEntries counter')
                output_list.append(f'merge_pacs_ss_AnetCommunicatorEntries{{server="{servername}",ActiveThreadType="processed"}} {AnetCommunicatorEntries_Processed}')
                output_list.append(f'merge_pacs_ss_AnetCommunicatorEntries{{server="{servername}",ActiveThreadType="queued"}} {AnetCommunicatorEntries_Queued}')
                output_list.append(f'merge_pacs_ss_AnetCommunicatorEntries{{server="{servername}",ActiveThreadType="wait"}} {AnetCommunicatorEntries_Wait}')
                output_list.append(f'merge_pacs_ss_AnetCommunicatorEntries{{server="{servername}",ActiveThreadType="failed"}} {AnetCommunicatorEntries_Failed}')
                output_list.append('')

            #AnetCommunicator
            try:
                u = re.search(r'AnetCommunicator</TD>\n<TD>(?P<a>\d+)</TD>\n<TD>(?P<b>\d+)/(?P<c>\d+)/(?P<d>\d+)</TD>', r.text)
                AnetCommunicator_Processed = u.group('a')
                AnetCommunicator_Queued = u.group('b')
                AnetCommunicator_Wait = u.group('c')
                AnetCommunicator_Failed = u.group('d')
            except:
                pass
            else:
                #print
                output_list.append(f'# HELP merge_pacs_ss_AnetCommunicator from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_AnetCommunicator counter')
                output_list.append(f'merge_pacs_ss_AnetCommunicator{{server="{servername}",ActiveThreadType="processed"}} {AnetCommunicator_Processed}')
                output_list.append(f'merge_pacs_ss_AnetCommunicator{{server="{servername}",ActiveThreadType="queued"}} {AnetCommunicator_Queued}')
                output_list.append(f'merge_pacs_ss_AnetCommunicator{{server="{servername}",ActiveThreadType="wait"}} {AnetCommunicator_Wait}')
                output_list.append(f'merge_pacs_ss_AnetCommunicator{{server="{servername}",ActiveThreadType="failed"}} {AnetCommunicator_Failed}')
                output_list.append('')

            #Jobs blocked
            try:
                u = re.search(r'BlockedList">(?P<Jobs_Blocked>\d+)<', r.text)
                Jobs_Blocked = u.group('Jobs_Blocked')
            except:
                pass
            else:
                #Print
                output_list.append(f'# HELP merge_pacs_ss_Jobs_Blocked various blocked jobs from Scheduler service port 11098')
                output_list.append(f'# TYPE merge_pacs_ss_Jobs_Blocked gauge')
                output_list.append(f'merge_pacs_ss_Jobs_Blocked{{server="{servername}"}} {Jobs_Blocked}')
                output_list.append('')

    # List of servers to check for status data For Appliction server
    server_list_5 = [
            'mergepacsprd',
            'mergepacscnt',
            'mergepacstest',
            'mergepacsrel',
    ]

    for servername in server_list_5:
        try:
 
            url = f'http://{servername}/servlet/AppServerMonitor'

            # Start the session
            session = requests.Session()

            # Create the payload
            payload = {'amicasUsername':'merge', 
                        'password':'H3@lthp@rtn3rsP@C5',
                        'domain':'healthpartners',
                        'submitButton':'Login'
                    }

            # Post the payload to the site to log in
            s = session.post(url, data=payload)

            # Navigate to the next page and scrape the data
            r = session.get(url)
        except:
            pass

        else:
            #Active and Idle DB connections
            try:
                s = re.search(r'connections: (?P<db_total>\d+) \((?P<db_idle>\d+)', r.text)
                db_active = int(s.group('db_total')) - int(s.group('db_idle'))
                active = db_active
                idle = s.group('db_idle')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_as_database_connections_active active database connections from Application server')
                output_list.append(f'# TYPE merge_pacs_as_database_connections_active gauge')
                output_list.append(f'merge_pacs_as_database_connections_active{{server="{servername}"}} {active}')
                output_list.append(f'# HELP merge_pacs_as_database_connections_idle idle database connections from Application server')
                output_list.append(f'# TYPE merge_pacs_as_database_connections_idle gauge')
                output_list.append(f'merge_pacs_as_database_connections_idle{{server="{servername}"}} {idle}')
                output_list.append('')
            #server Up time
            try:
                try:
                    u = re.search(r'up time: (?P<seconds>\d+)s', r.text)
                    seconds = int(u.group('seconds'))
                    up_time = (total_seconds / 3600)
                except:
                    pass

                try:
                    u = re.search(r'up time: (?P<minutes>\d+)m(?P<seconds>\d+)s', r.text)
                    minutes = int(u.group('minutes'))
                    seconds = int(u.group('seconds'))
                    total_seconds = ((minutes * 60) + seconds)
                    up_time = (total_seconds / 3600)
                except:
                    pass

                try:
                    u = re.search(r'up time: (?P<hours>\d+)h(?P<minutes>\d+)m(?P<seconds>\d+)s', r.text)
                    hours = int(u.group('hours'))
                    minutes = int(u.group('minutes'))
                    seconds = int(u.group('seconds'))
                    total_seconds = ((minutes * 60) + seconds)
                    total_hours = (total_seconds / 3600)
                    up_time = hours + total_hours
                except:
                    pass
            except:
                pass
            else:  
                output_list.append(f'# HELP merge_pacs_as_server_uptime server continously running since how many hours from Application server')
                output_list.append(f'# TYPE merge_pacs_as_server_uptime gauge')
                output_list.append(f'merge_pacs_as_database_server_uptime{{server="{servername}"}} {up_time}')
                output_list.append('')

            #memory usage
            try:
                u = re.search(r'Java (?P<java_current>\d+)MB\/(?P<java_peak>\d+)MB.*Native (?P<native_current>\d+)MB\/(?P<native_peak>\d+)MB.*Process Total (?P<process_current>\d+)MB\/(?P<process_peak>\d+)MB', r.text)
                java_current = u.group('java_current')
                java_peak = u.group('java_peak')
                native_current = u.group('native_current')
                native_peak = u.group('native_peak')
                process_current = u.group('process_current')
                process_peak = u.group('process_peak')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_as_memory_usage server usage of memory for various types from Application server')
                output_list.append(f'# TYPE merge_pacs_as_memory_usage counter')
                output_list.append(f'merge_pacs_as_memory_usage{{server="{servername}",memoryType="java_current"}} {java_current}')
                output_list.append(f'merge_pacs_as_memory_usage{{server="{servername}",memoryType="java_peak"}} {java_peak}')
                output_list.append(f'merge_pacs_as_memory_usage{{server="{servername}",memoryType="native_current"}} {native_current}')
                output_list.append(f'merge_pacs_as_memory_usage{{server="{servername}",memoryType="native_peak"}} {native_peak}')
                output_list.append(f'merge_pacs_as_memory_usage{{server="{servername}",memoryType="process_current"}} {process_current}')
                output_list.append(f'merge_pacs_as_memory_usage{{server="{servername}",memoryType="process_peak"}} {process_peak}')
                output_list.append('')

            output_list.append(f'# HELP merge_pacs_as_average_query_duration studysearch query average duration in last fifteen seconds from Application server')
            output_list.append(f'# TYPE merge_pacs_as_average_query_duration gauge')
            
            #Pattern Match
            try:
                # datetime object containing current date and time
                now = datetime.now()
                delay = now - timedelta(seconds=15)

                # mm/dd/YY H:M:S
                #dt_string_now = now.strftime("%m/%d/%Y %H:%M:%S")
                #dt_string_delay = delay.strftime("%m/%d/%Y %H:%M:%S")


                matching_lines = re.findall(r'<TD>StudySearch</TD>\n<TD>.*</TD>\n<TD>.*</TD>\n<TD>.*</TD>\n<TD>(?P<duration>\d+) (?P<duration_ms_s>ms|s)</TD>\n<TD>(?P<start_time>[\d\/\s\:\.]+)</TD>', r.text)
                if matching_lines:
                    total_duration = 0
                    total_count = 0
                    for line in matching_lines:
                        line_timestamp_str = line[2] #extract third value which is timestamp 
                        line_duration = int(line[0]) #extract first value which is duration
                        line_duration_ms_s = line[1] #extract second value which is ms or s

                        line_timestamp = datetime.strptime(line_timestamp_str, '%m/%d/%Y %H:%M:%S') #02/28/2022 13:03:10

                        if line_duration_ms_s == 's':
                            line_duration = line_duration * 1000

                        if line_timestamp >= delay:
                            total_duration = total_duration + line_duration
                            total_count = total_count + 1

                    if total_count > 0:
                        average_duration = total_duration / total_count

                output_list.append(f'merge_pacs_as_average_query_duration{{server="{servername}"}} {average_duration}')
                output_list.append('')
            except:
                pass
    
    # List of servers to check for status data For Sender 11110
    server_list_6 = [
            'mergepacsprd',
            'mergepacscnt',
            'mergepacstest',
            'mergepacsrel',
    ]

    for servername in server_list_6:
        url = f'http://{servername}:11110/serverStatus'
        try:
            r = requests.get(url)
            
            
        except:
            pass
        else:
            
            #Active and Idle DB connections
            try:
                s = re.search(r'connections: (?P<db_total>\d+) \((?P<db_idle>\d+)', r.text)
                db_active = int(s.group('db_total')) - int(s.group('db_idle'))
                active = db_active
                idle = s.group('db_idle')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_srs_database_connections_active active database connections from Sender service port 11110')
                output_list.append(f'# TYPE merge_pacs_srs_database_connections_active gauge')
                output_list.append(f'merge_pacs_srs_database_connections_active{{server="{servername}"}} {active}')
                output_list.append(f'# HELP merge_pacs_srs_database_connections_idle idle database connections from Sender service port 11110')
                output_list.append(f'# TYPE merge_pacs_srs_database_connections_idle gauge')
                output_list.append(f'merge_pacs_srs_database_connections_idle{{server="{servername}"}} {idle}')
                output_list.append('')
            #server Up time
            try:
                try:
                    u = re.search(r'up time: (?P<seconds>\d+)s', r.text)
                    seconds = int(u.group('seconds'))
                    up_time = (total_seconds / 3600)
                except:
                    pass

                try:
                    u = re.search(r'up time: (?P<minutes>\d+)m(?P<seconds>\d+)s', r.text)
                    minutes = int(u.group('minutes'))
                    seconds = int(u.group('seconds'))
                    total_seconds = ((minutes * 60) + seconds)
                    up_time = (total_seconds / 3600)
                except:
                    pass

                try:
                    u = re.search(r'up time: (?P<hours>\d+)h(?P<minutes>\d+)m(?P<seconds>\d+)s', r.text)
                    hours = int(u.group('hours'))
                    minutes = int(u.group('minutes'))
                    seconds = int(u.group('seconds'))
                    total_seconds = ((minutes * 60) + seconds)
                    total_hours = (total_seconds / 3600)
                    up_time = hours + total_hours
                except:
                    pass
            except:
                pass
            else:  
                output_list.append(f'# HELP merge_pacs_srs_server_uptime server continously running since how many hours from Sender service port 11110')
                output_list.append(f'# TYPE merge_pacs_srs_server_uptime gauge')
                output_list.append(f'merge_pacs_srs_database_server_uptime{{server="{servername}"}} {up_time}')
                output_list.append('')

            #memory usage
            try:
                u = re.search(r'Java (?P<java_current>\d+)MB\/(?P<java_peak>\d+)MB.*Native (?P<native_current>\d+)MB\/(?P<native_peak>\d+)MB.*Process Total (?P<process_current>\d+)MB\/(?P<process_peak>\d+)MB', r.text)
                java_current = u.group('java_current')
                java_peak = u.group('java_peak')
                native_current = u.group('native_current')
                native_peak = u.group('native_peak')
                process_current = u.group('process_current')
                process_peak = u.group('process_peak')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_srs_memory_usage server usage of memory for various types from Sender service port 11110')
                output_list.append(f'# TYPE merge_pacs_srs_memory_usage counter')
                output_list.append(f'merge_pacs_srs_memory_usage{{server="{servername}",memoryType="java_current"}} {java_current}')
                output_list.append(f'merge_pacs_srs_memory_usage{{server="{servername}",memoryType="java_peak"}} {java_peak}')
                output_list.append(f'merge_pacs_srs_memory_usage{{server="{servername}",memoryType="native_current"}} {native_current}')
                output_list.append(f'merge_pacs_srs_memory_usage{{server="{servername}",memoryType="native_peak"}} {native_peak}')
                output_list.append(f'merge_pacs_srs_memory_usage{{server="{servername}",memoryType="process_current"}} {process_current}')
                output_list.append(f'merge_pacs_srs_memory_usage{{server="{servername}",memoryType="process_peak"}} {process_peak}')
                output_list.append('')
            
            #SenderJobQueue
            try:
                u = re.search(r'Sender Job Queue Summary: New\((?P<new>\d+)\), Inprogress\((?P<inprogress>\d+)\), Error\((?P<error>\d+)\)', r.text)
                sender_new = u.group('new')
                sender_inprogress = u.group('inprogress')
                sender_error = u.group('error')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_srs_memory_usage server usage of memory for various types from Sender service port 11110')
                output_list.append(f'# TYPE merge_pacs_srs_memory_usage counter')
                output_list.append(f'merge_pacs_srs_sender_new{{server="{servername}"}} {sender_new}')
                output_list.append(f'merge_pacs_srs_sender_inprogress{{server="{servername}"}} {sender_inprogress}')
                output_list.append(f'merge_pacs_srs_sender_error{{server="{servername}"}} {sender_error}')

    # List of servers to check for status data For messaging server
    server_list_7 = [
            'mergepacsprd',
            'mergepacscnt',
            'mergepacstest',
            'mergepacsrel',
    ]

    for servername in server_list_7:
        url = f'http://{servername}:11104/serverStatus'
        try:
            r = requests.get(url)
            
            
        except:
            pass
        else:
            
            #Active and Idle DB connections
            try:
                s = re.search(r'connections: (?P<db_total>\d+) \((?P<db_idle>\d+)', r.text)
                db_active = int(s.group('db_total')) - int(s.group('db_idle'))
                active = db_active
                idle = s.group('db_idle')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_msgs_database_connections_active active database connections from messaging server port 11104')
                output_list.append(f'# TYPE merge_pacs_msgs_database_connections_active gauge')
                output_list.append(f'merge_pacs_msgs_database_connections_active{{server="{servername}"}} {active}')
                output_list.append(f'# HELP merge_pacs_msgs_database_connections_idle idle database connections from messaging server port 11104')
                output_list.append(f'# TYPE merge_pacs_msgs_database_connections_idle gauge')
                output_list.append(f'merge_pacs_msgs_database_connections_idle{{server="{servername}"}} {idle}')
                output_list.append('')
            #server Up time
            try:
                try:
                    u = re.search(r'up time: (?P<seconds>\d+)s', r.text)
                    seconds = int(u.group('seconds'))
                    up_time = (total_seconds / 3600)
                except:
                    pass

                try:
                    u = re.search(r'up time: (?P<minutes>\d+)m(?P<seconds>\d+)s', r.text)
                    minutes = int(u.group('minutes'))
                    seconds = int(u.group('seconds'))
                    total_seconds = ((minutes * 60) + seconds)
                    up_time = (total_seconds / 3600)
                except:
                    pass

                try:
                    u = re.search(r'up time: (?P<hours>\d+)h(?P<minutes>\d+)m(?P<seconds>\d+)s', r.text)
                    hours = int(u.group('hours'))
                    minutes = int(u.group('minutes'))
                    seconds = int(u.group('seconds'))
                    total_seconds = ((minutes * 60) + seconds)
                    total_hours = (total_seconds / 3600)
                    up_time = hours + total_hours
                except:
                    pass
            except:
                pass
            else:  
                output_list.append(f'# HELP merge_pacs_msgs_server_uptime server continously running since how many hours from messaging server port 11104')
                output_list.append(f'# TYPE merge_pacs_msgs_server_uptime gauge')
                output_list.append(f'merge_pacs_msgs_database_server_uptime{{server="{servername}"}} {up_time}')
                output_list.append('')

            #memory usage
            try:
                u = re.search(r'Java (?P<java_current>\d+)MB\/(?P<java_peak>\d+)MB.*Native (?P<native_current>\d+)MB\/(?P<native_peak>\d+)MB.*Process Total (?P<process_current>\d+)MB\/(?P<process_peak>\d+)MB', r.text)
                java_current = u.group('java_current')
                java_peak = u.group('java_peak')
                native_current = u.group('native_current')
                native_peak = u.group('native_peak')
                process_current = u.group('process_current')
                process_peak = u.group('process_peak')
            except:
                pass
            else:
                output_list.append(f'# HELP merge_pacs_msgs_memory_usage server usage of memory for various types from messaging server port 11104')
                output_list.append(f'# TYPE merge_pacs_msgs_memory_usage counter')
                output_list.append(f'merge_pacs_msgs_memory_usage{{server="{servername}",memoryType="java_current"}} {java_current}')
                output_list.append(f'merge_pacs_msgs_memory_usage{{server="{servername}",memoryType="java_peak"}} {java_peak}')
                output_list.append(f'merge_pacs_msgs_memory_usage{{server="{servername}",memoryType="native_current"}} {native_current}')
                output_list.append(f'merge_pacs_msgs_memory_usage{{server="{servername}",memoryType="native_peak"}} {native_peak}')
                output_list.append(f'merge_pacs_msgs_memory_usage{{server="{servername}",memoryType="process_current"}} {process_current}')
                output_list.append(f'merge_pacs_msgs_memory_usage{{server="{servername}",memoryType="process_peak"}} {process_peak}')
                output_list.append('')
            
            #MessageCountInfoforQueueType
            output_list.append(f'# HELP merge_pacs_msgs_message_count server usage of memory for various types from messaging server port 11104')
            output_list.append(f'# TYPE merge_pacs_msgs_msgs_message_count counter')
            u = re.search(r'DLQ</a></TD>\n<TD>Queue</TD>\n<TD>(?P<dlq>\d+)</TD>', r.text)
            if u:
                DLQ = u.group('dlq')
                output_list.append(f'merge_pacs_msgs_msgs_message_count{{server="{servername}",QueueType="dlq"}} {DLQ}')

            u = re.search(r'ExpiryQueue</a></TD>\n<TD>Queue</TD>\n<TD>(?P<ExpiryQueue>\d+)</TD>', r.text)
            if u:
                Expiry_queue = u.group('ExpiryQueue')
                output_list.append(f'merge_pacs_msgs_msgs_message_count{{server="{servername}",QueueType="expiry"}} {Expiry_queue}')

            u = re.search(r'Event.EANotificationProcessor</a></TD>\n<TD>Queue</TD>\n<TD>(?P<EANotificationProcessor>\d+)</TD>', r.text)
            if u:
                EA_notification_processor = u.group('EANotificationProcessor')
                output_list.append(f'merge_pacs_msgs_msgs_message_count{{server="{servername}",QueueType="eanotificationprocessor"}} {EA_notification_processor}')
            
            u = re.search(r'EANotification</a></TD>\n<TD>Queue</TD>\n<TD>(?P<EANotification>\d+)</TD>', r.text)
            if u:
                EA_notification = u.group('EANotification')
                output_list.append(f'merge_pacs_msgs_msgs_message_count{{server="{servername}",QueueType="eanotification"}} {EA_notification}')

            u = re.search(r'WorklistRequest</a></TD>\n<TD>Queue</TD>\n<TD>(?P<WorklistRequest>\d+)</TD>', r.text)
            if u:
                worklistRequest = u.group('WorklistRequest')
                output_list.append(f'merge_pacs_msgs_msgs_message_count{{server="{servername}",QueueType="worklistreq"}} {worklistRequest}')

    # List of servers to check for status data For Appliction server
        server_list_8 = [
                'mergeeasec',
                'mergeeapri',
                'mergeeatest',
                'mergeeatestcnt',
        ]

    for servername in server_list_8:
        try:
        
            APP_USERNAME = 'merge'
            APP_PASSWORD = 'H3@lthp@rtn3rsP@C5'

            sess = requests.Session()

            login_url = f'https://{servername}/eaweb/login'
            r = sess.get(login_url, verify=False, timeout=DEFAULT_HTTP_TIMEOUT)

            # Raise an error if we get an "erorr" http status (e.g. 404)
            r.raise_for_status()


            # Parse content and get the hidden _csrf token
            soup=BeautifulSoup(r.content)
            csrfToken = soup.find("input",{"name":"_csrf"})['value']

            # Contruct login form submission payload
            payload = {
                'username' : APP_USERNAME,
                'password':APP_PASSWORD,
                'ldapDomain':'1',       # Assume that 'healthpartners.int' is the only option other than Local
                '_csrf': csrfToken
            }


            post = sess.post(login_url, data=payload, verify=False, timeout=DEFAULT_HTTP_TIMEOUT)
            post.raise_for_status
        

            current_unix_timestamp = int(time.time()*1000)

            # Then this
            execute_jquery_url = f'https://{servername}/eaweb/monitoring/scheduledwork/getsummaryresult?componentName=&taskName=&status=&_filterByGroupFlag=on&_actionGroupsFlag=on&groupIdentifier=&selectedAction=&singleCheckedItem=&nextAttemptDate=03%2F23%2F2022&nextAttemptTime=13%3A50&_csrf={csrfToken}'
            jquery_response = sess.get(execute_jquery_url, verify=False, timeout=DEFAULT_HTTP_TIMEOUT)

            # Note sure of the significance of the "draw=" argument to the function here. The page makes two calls with the value set to both 1 and 2. But setting it to 0 or ommitting it also seems to generate the same results.
            get_jquery_result_url = f'https://{servername}/eaweb/monitoring/scheduledwork/getsummarypaginationresults?draw=0&columns%5B0%5D.data=Select&columns%5B0%5D.name=&columns%5B0%5D.searchable=true&columns%5B0%5D.orderable=false&columns%5B0%5D.search.value=&columns%5B0%5D.search.regex=false&columns%5B1%5D.data=componentName&columns%5B1%5D.name=&columns%5B1%5D.searchable=true&columns%5B1%5D.orderable=true&columns%5B1%5D.search.value=&columns%5B1%5D.search.regex=false&columns%5B2%5D.data=taskName&columns%5B2%5D.name=&columns%5B2%5D.searchable=true&columns%5B2%5D.orderable=true&columns%5B2%5D.search.value=&columns%5B2%5D.search.regex=false&columns%5B3%5D.data=groupIdentifier&columns%5B3%5D.name=&columns%5B3%5D.searchable=true&columns%5B3%5D.orderable=true&columns%5B3%5D.search.value=&columns%5B3%5D.search.regex=false&columns%5B4%5D.data=status&columns%5B4%5D.name=&columns%5B4%5D.searchable=true&columns%5B4%5D.orderable=true&columns%5B4%5D.search.value=&columns%5B4%5D.search.regex=false&columns%5B5%5D.data=count&columns%5B5%5D.name=&columns%5B5%5D.searchable=true&columns%5B5%5D.orderable=false&columns%5B5%5D.search.value=&columns%5B5%5D.search.regex=false&order%5B0%5D.column=1&order%5B0%5D.dir=asc&start=0&length=50&search.value=&search.regex=false&_={current_unix_timestamp}'
            get_jquery_result_result = sess.get(get_jquery_result_url, verify=False, timeout=DEFAULT_HTTP_TIMEOUT)
            jsonResponse = get_jquery_result_result.json()

        except:
            pass

        else:
            #MessageCountInfoforQueueType
            output_list.append(f'# HELP merge_pacs_ea_schedule_work_engine ea scheduleworkengine numbers')
            output_list.append(f'# TYPE merge_pacs_ea_schedule_work_engine counter')
            for data_item in jsonResponse['data']:
                output_list.append(f'merge_pacs_ea_schedule_work_engine{{server="{servername}",componentName="{data_item["componentName"]}",taskname="{data_item["taskName"]}",status="{data_item["status"]}"}} {data_item["count"]}')
        output_list.append('')

    output_list.append('')

    # Get ending time and calculate time in sec (x.xx) it took the script to run
    endtime = datetime.now()
    duration = endtime - starttime      # The amount of time between when we started gathering data and when we ended.
    
    output_list.append(f'# Script ended {datetime.ctime(endtime)}')
    output_list.append(f'# Script execution duration {str(duration.seconds)}.{str(duration.microseconds)[:-4]} seconds')


    return output_list

if __name__ == "__main__":
    metrics_list = main()

    for line in metrics_list:
        print(line)