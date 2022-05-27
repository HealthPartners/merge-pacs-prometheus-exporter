# Summary of Scripts in this Folder
* **merge_pacs_metric_to_prometheus_service.py** - Script that is meant to be installed and run as a service on each Merge PACS server. Provides a prometheus exporter that hosts data on port 7601 of the server itself.

## merge_pacs_metric_to_prometheus_service.py
### Purpose
Collects metrics data from the locally hosted pages that Merge PACS processes expose and reformats the data into prometheus formatting. The script can be installed and run as a service so that it will continue functioning indefinitely. It starts its own web server that exposes the data on port 7601.

### Prerequistes before first use
1) Of course python must be installed. Install it for all users and choose the "Install py launcher" option.
    * Run the Python installer
    * Select the checkboxs to "Add Python to Path" and "Install for all users"
    * Choose Customize Installation
        * Under Optional Features: Ensure the options to install py launcher for all users are selected
        * Under Advanced Options: Choose "Install for all users" and "Add Python to environment variables" and "Create shortcuts for installed applications" if not already selected

1) Install the required client packages. 
    1) First update pip, then install required packages. To do this, run a cmd prompt as your SA account, then:
    ```
    pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org
    ```
    1) Install required packages
    ```
    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org prometheus_client pandas requests lxml pywin32
    ```
    1) Run the PyWin32 post-install script (update the **Python310** part to match your version number)
    ```
    python "c:\program files\Python310\Scripts\pywin32_postinstall.py" -install
    ```
 \* Note the "trusted-host" part may be required on servers because python doesn't recognize the HP SSL certificate that the NetScalers use for SSL inspection

### Deployment Steps
* Copy the updated script from GitLab to the K:\HPMetrics folder on each server
* From a command prompt on the target server, run these commands: 
```
python k:\HPmetrics\merge_pacs_metrics_to_prometheus_service.py stop     (this will error out if the service has NEVER run on this server before)
python k:\HPmetrics\merge_pacs_metrics_to_prometheus_service.py remove     (this will error out if the service has NEVER run on this server before)
python k:\HPmetrics\merge_pacs_metrics_to_prometheus_service.py install
python k:\HPmetrics\merge_pacs_metrics_to_prometheus_service.py start
sc config HealthPartnersMetricsService start=Auto
```
