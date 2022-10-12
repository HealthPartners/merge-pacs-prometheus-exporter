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
    1) First update pip, then install required packages. To do this, run a cmd prompt as your adminitrator account, then:
    ```
    pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org
    ```
    1) Install required packages
    ```
    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org prometheus_client pandas requests pywin32
    ```
    1) Run the PyWin32 post-install script (update the **Python310** part to match your version number)
    ```
    python "c:\program files\Python310\Scripts\pywin32_postinstall.py" -install
    ```
 \* Note the "trusted-host" part may be required on servers because python doesn't recognize the HP SSL certificate that the NetScalers use for SSL inspection

### Deployment Steps
* Copy the python package to a convenient location
* Create a config.ini file in the package base location (alongside README.md) with unique local settings (you can use config.ini.example as a starting point)
* From a command prompt on the target server, run these commands: 
```
python -m merge_pacs_metrics_prometheus_exporter stop     (this will error out if the service has NEVER run on this server before)
python -m merge_pacs_metrics_prometheus_exporter remove     (this will error out if the service has NEVER run on this server before)
python -m merge_pacs_metrics_prometheus_exporter install
python -m merge_pacs_metrics_prometheus_exporter start
sc config MergePACSPrometheusExporter start=Auto
```

If you've changed the value of the Service Name in the ```config.ini``` file, you'll need to substitute that in the sc line above