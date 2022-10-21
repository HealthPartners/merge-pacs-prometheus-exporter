""" 
Purpose:
    Collect and log metrics from the locally hosted pages that Merge PACS processes expose. Reformat the data into Prometheus formatting.

 """

#from this import d
from .config import CONF
from .__init__ import __version__
from .metrics_classes import ExporterSelfMetrics, MessagingServerAppMetrics, WorklistServerAppMetrics, ClientMessagingServerAppMetrics, \
        ApplicationServerAppMetrics, EANotificationProcessorAppMetrics, SchedulerAppMetrics, SenderAppMetrics
import argparse
#from datetime import datetime
import logging
import os
#import pandas
from prometheus_client import start_http_server
#import re
#import requests
import servicemanager
import socket
import sys
import time
import win32event
import win32service 
import win32serviceutil


"""
General steps:
    Set global definitions for some static information (http port, log level, etc.)
    In main():
        Initialize new classes of AppMetrics -- one new class per service to monitor (***AppMetrics.__init__)
            Declare the metric definitions for this service
        Start the http mini server process to serve metric results on configured port
        Run an infinite loop to refresh the metric data from source every polling interval
            Fetch and format metrics data for each metric (***AppMetrics.fetch)
                Connect to services's local http port
                Parse output for each service
                Assign output to metrics
            [repeat loop]

"""

##
## General Definitions
##

# Current software version
CURRENT_VERSION = __version__

# Set logging parameters
# Change level to print more or fewer debugging messages
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _initialize_metric_classes(
    messaging_server_metric_url = f'http://localhost:11104/serverStatus',
    worklist_server_metric_url = 'http://localhost:11108/serverStatus',
    client_messaging_server_metric_url = 'http://localhost:11109/serverStatus',
    application_server_metric_url = 'http://localhost/servlet/AppServerMonitor',
    ea_notification_processor_metric_url =' http://localhost:11111/serverStatus',
    scheduler_metric_url = 'http://localhost:11098/serverStatus',
    sender_metric_url = 'http://localhost:11110/serverStatus',
    server_name_label = os.getenv('COMPUTERNAME', 'merge_pacs_unknown_server').lower()
):
    """
    Initialize each of the promtheus_client classes for each of the metrics we're going to collect. 
    Arguments: Optional list of specific URLs to use for each metric service (otherwise defaults to localhost)
    Returns: A list of class objects initialized. Use these objects to call the fetch() method for each one to 
        populate the registry with metric values.
    """

    metric_class_objects = []

    exporter_self_metrics = ExporterSelfMetrics(metric_url=None, \
        metric_server_label=server_name_label, metric_service_name=f'{sys.argv[0]} self metrics', metric_prefix='merge_pacs_exporter')
    metric_class_objects.append(exporter_self_metrics)

    messaging_server_app_metrics = MessagingServerAppMetrics(metric_url=messaging_server_metric_url, \
        metric_server_label=server_name_label, metric_service_name='Messaging Server', metric_prefix='merge_pacs_msgs')
    metric_class_objects.append(messaging_server_app_metrics)

    worklist_server_app_metrics = WorklistServerAppMetrics(metric_url=worklist_server_metric_url, \
        metric_server_label=server_name_label, metric_service_name='Worklist Server', metric_prefix='merge_pacs_ws')
    metric_class_objects.append(worklist_server_app_metrics)
    
    client_messaging_server_app_metrics = ClientMessagingServerAppMetrics(metric_url=client_messaging_server_metric_url, \
        metric_server_label=server_name_label, metric_service_name='Client Messaging Server', metric_prefix='merge_pacs_cms')
    metric_class_objects.append(client_messaging_server_app_metrics)

    application_server_app_metrics = ApplicationServerAppMetrics(metric_url=application_server_metric_url, \
        metric_server_label=server_name_label, metric_service_name='Application (MergePACSWeb) Server (/servlet/AppServerMonitor)', \
        metric_prefix='merge_pacs_as', metric_username=CONF.APP_USERNAME, metric_password=CONF.APP_PASSWORD, metric_domain=CONF.APP_DOMAIN)
    metric_class_objects.append(application_server_app_metrics)

    ea_notification_procesor_app_metrics = EANotificationProcessorAppMetrics(metric_url=ea_notification_processor_metric_url, \
        metric_server_label=server_name_label, metric_service_name='EA Notification Processor', metric_prefix='merge_pacs_eanp')
    metric_class_objects.append(ea_notification_procesor_app_metrics)

    scheduler_app_metrics = SchedulerAppMetrics(metric_url=scheduler_metric_url, \
        metric_server_label=server_name_label, metric_service_name='Scheduler', metric_prefix='merge_pacs_scheds')
    metric_class_objects.append(scheduler_app_metrics)

    sender_app_metrics = SenderAppMetrics(metric_url=sender_metric_url, \
        metric_server_label=server_name_label, metric_service_name='Sender', metric_prefix='merge_pacs_sends')
    metric_class_objects.append(sender_app_metrics)

    return metric_class_objects

def fetch_metrics(metric_objects):
    """
    Given a list of metric class objects, call the .fetch() method for each to refresh its metrics values
    """
    logging.info(f'### Starting metric collection for this iteration ###')

    logging.info(f'#   Reading configuration values')

    for metric_object in metric_objects:
        try:
            metric_object.fetch(http_request_timeout=CONF.HTTP_TIMEOUT)
        except:
            logging.error(f'Failed to call the fetch() method for object of class {metric_object.__class__.__name__}')
            logging.raiseExceptions

    logging.info(f'### End metric collection for this iteration. Sleeping for {CONF.POLLING_INTERVAL_SECONDS} seconds. ###')



class RunMetricsService(win32serviceutil.ServiceFramework):
    """ Options to install, run, start and restart this application as a Windows service
        See: https://stackoverflow.com/questions/69008155/run-python-script-as-a-windows-service
    """
    logging.debug(f'Starting RunMetricsService class')

    # I would love to make this class have the service name be more dynamic so it could be configurable, but I can't
    # figure out how to make it work. The problem is that when PythonService is called to run this code as a Windows service
    # I think it is calling directly into this class. It doesn't pass in the service name that's being called, so we have
    # to know the name in order to get the path to the config file from the registry, e.g.
    # HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\MergePACSMetricsPrometheusExporter\Parameters\CustomConfigFile
    _svc_name_ = 'MergePACSMetricsPrometheusExporter'

    # # Load configuration values from any supplied configuration files and update CONF() configuration class
    # logging.debug(f'Loading configurations in {__name__}')
    # CONF.load_configurations(win32serviceutil.GetServiceCustomOption('MergePACSPrometheusExporter','CustomConfigFile', None))

    _svc_display_name_ = CONF.SERVICE_DISPLAY_NAME
    _svc_description_ = CONF.SERVICE_DESCRIPTION
  
    # runtime_config = CONF

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)

    @classmethod
    def parse_command_line(cls, service_args = sys.argv, servicename=_svc_name_):
        """
        Parses the command line options in argv or the provided alternate list of arguments (service_args). Also accepts
        a string of any additional command line arguments that should be given to the exporter script when it runs.
        """
        # Load configuration values from any supplied configuration files and update CONF() configuration class
        CONF.load_configurations(win32serviceutil.GetServiceCustomOption(servicename,'CustomConfigFile', None))
        win32serviceutil.HandleCommandLine(cls, argv = service_args)

    @classmethod
    def install(cls, service_args = sys.argv, custom_config_file=None):
        logging.info('Installing the metrics service')
        if custom_config_file == '' or custom_config_file is None:
            logging.info(f'No configuration file provided')
        else:
            cls._update_config_file_path(custom_config_file)

        win32serviceutil.HandleCommandLine(cls, argv=service_args)

    @classmethod
    def update(cls, service_args = sys.argv, custom_config_file=None):
        logging.info('Updating the metrics service')
        cls._update_config_file_path(custom_config_file)
        win32serviceutil.HandleCommandLine(cls, argv=service_args)

    @classmethod
    def _update_config_file_path(cls, custom_config_file):
        try:
            CONF.load_configurations(custom_config_file)
        except:
            logging.warn(f'Error processing custom configuration file. Not updating the configuration path for the service.')
        else:
            logging.info(f'Setting custom configuration file location to: {custom_config_file}')
            win32serviceutil.SetServiceCustomOption(cls, 'CustomConfigFile', custom_config_file)

    def SvcStop(self):
        self.stop()
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        self.start()
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        self.main()

    def start(self):
        self.isrunning = True

    def stop(self):
       self.isrunning = False

    def main(self):
        # Call function to return a list of metric class objects that are initialized and ready to populate with data using each
        # object's fetch method
        
        config_file_path = win32serviceutil.GetServiceCustomOption(self._svc_name_,'CustomConfigFile', None)
        # Load configuration values from any supplied configuration files and update CONF() configuration class
        CONF.load_configurations(config_file_path)

        self._svc_display_name_ = CONF.SERVICE_DISPLAY_NAME
        self._svc_description_ = CONF.SERVICE_DESCRIPTION

        metric_objects = _initialize_metric_classes()
        
        # Start up the http mini-server
        logging.info(f'Starting http server on port {CONF.HOSTING_PORT}')
        start_http_server(CONF.HOSTING_PORT)
        #logging.info(f'Starting http server on port {self.runtime_config.HOSTING_PORT}')
        #start_http_server(self.runtime_config.HOSTING_PORT)

        while self.isrunning:
            # Start the loop that will refresh the metrics at every polling interval. 
            fetch_metrics(metric_objects)
            
            wait_seconds = 0     # reset the wait counter

            while wait_seconds < CONF.POLLING_INTERVAL_SECONDS and self.isrunning:
                #time.sleep(POLLING_INTERVAL_SECONDS)
                time.sleep(1)   # check self.isrunning every 1 second to be able to break out the loop faster
                wait_seconds = wait_seconds + 1

            # Reload values in the CONF class at the end of the interval
            CONF.load_configurations(config_file_path)

        logging.info('Service stop received. Terminating loop.')


def main():
    """Main entry point
    
    There is an option to run the code without going through the windows service process mainly for debugging. You can
    also optionally provide a second argument in this mode to target a server other than the localhost. But this option
    isn't very helpful after Merge PACS v8 because the service status URLs are not available remotely.

    Useage:

        python -m merge_pacs_metrics_prometheus_exporter noservice
            OR
        python -m merge_pacs_metrics_prometheus_exporter [options] install|update|remove|start [...]|stop|restart [...]|debug [...]
    
    """
    logging.debug('argv = %s' % sys.argv)

    logging.info(f'Running merge_pacs_metrics_prometheus_exporter version {CURRENT_VERSION}')

    program_name = 'python -m merge_pacs_metrics_prometheus_exporter'

    parser = argparse.ArgumentParser(description='The merge_pacs_metrics_prometheus_exporter python module helps to scrape metrics from \
        a Merge PACS server and present them in prometheus format',
        prog=program_name
    )

    parser.add_argument('--noservice', action='store_true', help='Run the script without installing the service. Useful for troubleshooting to view activity output on the console')
    parser.add_argument('--configfile', action='store', help='Path to a locally customized configuration file in stanadard ini format. Note this only works with the --noservice option')

    # Parse the command line options for one of the above known arguments. The remaining arguments will be passed through to the win32serviceutil.HandleCommandLine
    # function to be interested as service control commands. Known arguments will be in args[0] and remaining arguments will be in args[1]
    args = parser.parse_known_args()
    
    # Exporter args are the known argument to be consumed by this script. The other arguments that will be passed ton the win32serviceutil function
    exporter_args = args[0]

    # Get the absolute path to the user-supplied config file in the event the user supplied a relative one
    try:
        configfile = os.path.abspath(exporter_args.configfile)
    except:
        configfile = None

    # When passing arguments to the win32serviceutil function, it expects a list in "argv" format. In other words, [0] should be the
    # program name, then [1:] should be the actual arguments to process. On other words, all the other arguments that aren't defined above.
    service_args = [program_name] + args[1]

    if exporter_args.noservice:
        ### Run WITHOUT calling the service options to install, run, start and restart this application as a Windows service

        # Load from configuration inis, if provided
        CONF.load_configurations(file_path = configfile)

        # Initialize new classes to set up all of the class definitions, define the metrics, etc.
        metric_objects = _initialize_metric_classes()
        
        # Start up the http mini-server
        logging.info(f'Starting http server on port {CONF.HOSTING_PORT}')
        start_http_server(CONF.HOSTING_PORT)

        while True:
            # Start the loop that will refresh the metrics at every polling interval. 

            fetch_metrics(metric_objects)
            
            wait_seconds = 0     # reset the counter

            while wait_seconds < CONF.POLLING_INTERVAL_SECONDS:
                #time.sleep(POLLING_INTERVAL_SECONDS)
                time.sleep(1)   # check self.isrunning every 1 second to be able to break out the loop faster
                wait_seconds = wait_seconds + 1

            # Reload values in the CONF class at the end of the interval
            if exporter_args.configfile is not None:
                CONF.load_configurations(file_path = configfile)

        logging.warning('Somehow we have exited the metrics collection loop!')    

    else:
        # If the --noservice option IS NOT given, then pass the rest of the arguments to the win32serviceutil command 
        # to be interpreted as a start/stop/install/remove/debug/etc command for the service
        metric_service = RunMetricsService


        if 'install' in service_args:
            # in the case that we're installing the service. Provide path to the custom ini file so that the path can be updated in the registry.
            metric_service.install(service_args=service_args, custom_config_file=configfile)
        if 'update' in service_args:
            # in the case that we're updating the service. Provide path to the custom ini file so that the path can be updated in the registry.
            metric_service.install(service_args=service_args, custom_config_file=configfile)
        else:
            metric_service.parse_command_line(service_args=service_args)


    

if __name__ == "__main__":
    main()