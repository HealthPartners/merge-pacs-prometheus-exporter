import pandas as pd
import requests
from datetime import datetime
import re

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
            r = requests.get(url)
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

    # List of servers to check for status data
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


    # Get ending time and calculate time in sec (x.xx) it took the script to run
    endtime = datetime.now()
    duration = endtime - starttime      # The amount of time between when we started gathering data and when we ended.
    
    output_list.append(f'# Script ended {datetime.ctime(endtime)}')
    output_list.append(f'# Script execution duration {str(duration.seconds)}.{str(duration.microseconds)[:-4]} seconds')


    return output_list

if __name__ == "__main__":
    metrics_list = main()
    sep = '\n'
    print(sep.join(metrics_list))
