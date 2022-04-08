# Summary of Scripts in this Folder
* merge_pacs_metric_to_prometheus_service.py - Script that is meant to be installed and run as a service on each Merge PACS server. Provides a prometheus exporter that hosts data on port 7601 of the server itself.

## merge_pacs_metric_to_prometheus_service.py
## Purpose
Collects metrics data from the locally hosted pages that Merge PACS processes expose and reformats the data into prometheus formatting. The script can be installed and run as a service so that it will continue functioning indefinitely. It starts its own web server that exposes the data on port 7601.

## Prerequistes before first use
0) Of course python must be installed. Install it for all users and choose the "Install py launcher" option.
1) The prometheus_client package must be installed with 'pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org prometheus_client'
2) The pandas package must be installed with 'pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org pandas'
3) The requests package must be installed with 'pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org requests'
4) The lxml package must be installed with 'pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org lxml'
5) Install module pywin32
            * Note the "trusted-host" part may be required on servers because python doesn't recognize the HP SSL certificate that the NetScalers use for SSL inspection

### Deployement Steps
* Copy the updated script from GitLab to the K:\HPMetrics (shared as \\server\HPMetrics) folder on each server
* From a local command prompt, run these command for each server (using your SA account in place of "YOUR_SA"): 
** runas \\server -u YOUR_SA "k:\HPmetrics\merge_pacs_metrics_to_prometheus_service.py remove" (this will error out if the service has NEVER run on this server before)
** runas \\server -u YOUR_SA "k:\HPmetrics\merge_pacs_metrics_to_prometheus_service.py install"
** runas \\server -u YOUR_SA "k:\HPmetrics\merge_pacs_metrics_to_prometheus_service.py start"
** <need to set service to automatic>

