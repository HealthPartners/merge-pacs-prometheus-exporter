"""
Read configuration from config file.

A custom config.ini may be provided in this project's root directory (alongside the README.md) If not
found, a default configuration will be used.

We use the @property decorator to allow good-enough immutability in the state of the Config instance
and to allow reference-time evaluation of config values so that the configuration can be updated in the
configuration file and (optionally) updated when the configuration file is changed.
( see https://johndanielraines.medium.com/write-a-better-config-py-1a443cf5bb36)

These values can be referenced in other parts of this project by:
    from .config import config
    config_val = config.KEYNAME

"""
import configparser
import logging
import os
from os.path import dirname, join


_default_configpath = join(dirname(dirname(os.path.realpath(__file__))), "merge_pacs_metrics_prometheus_exporter", "default_config.ini")
_custom_configpath = join(dirname(dirname(os.path.realpath(__file__))), "config.ini")

class _Config:
    """
    Class to read and hold configuration values from both the default and, optionally, custom configuration files.
    """
    def __init__(self, file_path = None):
        self.config = configparser.ConfigParser()
        #self.load_configurations(file_path)

    def load_configurations(self, file_path = _custom_configpath):
        """
        Loads the default configuration values and any custom configuration from a provided filename
        """
        self._load_default_config()
        self._load_custom_config(file_path = file_path)

    def _load_default_config(self):
        """
        Load default configuration values from the default ini file provided with the package
        """
        logging.info(f'Reading configuration data from default location: {_default_configpath}')
        try:
            self.config.read_file(open(_default_configpath))
        except:
            logging.warning(f'Failed to read default configuration file {_default_configpath}. Using fallback values.')
            logging.raiseExceptions

    def _load_custom_config(self, file_path = _custom_configpath):
        """
        Load custom configuration values from the path provided
        """
        logging.info(f'Checking for custom configuration in {file_path}')
        try:
            dataset = self.config.read(file_path)
        except TypeError:
            # No file_path provided
            pass
        else:
            if len(dataset) == 0:
                logging.warning(f'Failed to find custom configuration file {file_path}. Using configuration default values only.')
            else:
                logging.info(f'Custom configuration values read')

    # General options
    @property
    def POLLING_INTERVAL_SECONDS(self):
        return self.config.getint('General','POLLING_INTERVAL_SECONDS', fallback=20)

    @property
    def HOSTING_PORT(self):
        return self.config.getint('General','HOSTING_PORT', fallback=8081)

    @property
    def METRICS_SERVER(self):
        return self.config.get('General', 'METRICS_HOSTNAME', fallback='localhost')

    @property
    def HTTP_TIMEOUT(self):
        return self.config.getfloat('General', 'HTTP_TIMEOUT', fallback=2.0)
    
    @property
    def METRICS_SERVER_LABEL(self):
        local_hostname = os.getenv('COMPUTERNAME', 'merge_pacs_unknown_server').lower()
        return self.config.get('General', 'METRICS_SERVER_LABEL', fallback=local_hostname)

    # Application-level options. Get the username/password/domain to use to log in to the application:
    @property
    def APP_USERNAME(self):
        return self.config.get('MergePACS', 'APP_USERNAME', fallback='merge')

    @property
    def APP_PASSWORD(self):
        return self.config.get('MergePACS', 'APP_PASSWORD', fallback='password')

    @property
    def APP_DOMAIN(self):
        return self.config.get('MergePACS', 'APP_DOMAIN', fallback='domain.int')

    # Service-related options
    @property
    def SERVICE_NAME(self):
        return self.config.get('Service', 'SERVICE_NAME', fallback='MergePACSPrometheusExporter')

    @property
    def SERVICE_DISPLAY_NAME(self):
        return self.config.get('Service', 'SERVICE_DISPLAY_NAME', fallback='Merge PACS Prometheus Exporter Service')

    @property
    def SERVICE_DESCRIPTION(self):
        return self.config.get('Service', 'SERVICE_DESCRIPTION', fallback='Customized service that exposes Merge PACS metric data in Prometheus format')


CONF = _Config()