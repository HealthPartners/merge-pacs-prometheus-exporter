from os.path import dirname, abspath
import logging

# Manually set each version increment here
__version__ = '4.0.0'

ROOT_DIR = dirname(abspath(__file__))


# Set default logging parameters
# Change level to print more or fewer debugging messages
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')