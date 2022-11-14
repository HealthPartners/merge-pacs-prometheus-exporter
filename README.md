## Merge PACS Metrics Exporter
Collects metrics data from the locally hosted pages that Merge PACS v7.x and v8.x processes expose and reformats the data into a Prometheus-compatible format. The script can be installed and run as a Windows service so that it will continue functioning indefinitely. It starts its own web server that exposes the data on a configurable port.

## Prerequistes before first use
1) Of course python must be installed. Install it for all users and choose the "Install py launcher" option. To make your life easier, follow the steps and options below.
    * Run the Python installer
    * Select the checkboxs to "Add Python to Path" and "Install for all users"
    * Choose Customize Installation
        * Under Optional Features: Ensure the options to install py launcher for all users are selected
        * Under Advanced Options: Choose "Install for all users" and "Add Python to environment variables" and "Create shortcuts for installed applications" if not already selected

1) Install the Merge PACS Metrics Prometheus Exporter package along with its dependencies.
    * Download and unzip this project to a convenient local folder
    * Use pip to install the package and dependencies
    ```
    python -m pip install \path\to\merge-pacs-metrics-prometheus-exporter
    ```
    
    If you receive and error similar to "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self signed certificate in certificate chain" it is probably because you have a firewall or other similar device that decrypts SSL traffic and re-encrypts it with your organization's self-signed certificate. This certificate is not trusted by pip. One way to circumvent this warning is to use the trusted-host option to ignore the certificate errors. But be aware that this could leave you vulnerable to a man-in-the-middle attack since you are not verifying the site sources. One way to use trusted-hosts is below.

    ```
    python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org \path\to\merge-pacs-metrics-prometheus-exporter
    ```

    * Run the PyWin32 post-install script (update the **Python310** part to match your version number, and provide the correct path to Python if you didn't install in Program Files)
    ```
    python "c:\Program Files\Python310\Scripts\pywin32_postinstall.py" -install
    ```

## Deployment Steps
* Create a config.ini file in the package base location (alongside README.md) with unique local settings (you can use .\docs\config.ini.example as a starting point). At a minimum, you'll need to provide a username and password that can be used to log into Merge PACS and view the http://localhost/servlet/AppServerMonitor page.
* From a command prompt on the server, run these commands: 
```
python -m merge_pacs_metrics_prometheus_exporter stop     (this will error out if the service has NEVER run on this server before)
python -m merge_pacs_metrics_prometheus_exporter remove     (this will error out if the service has NEVER run on this server before)
python -m merge_pacs_metrics_prometheus_exporter --startup auto install --configfile /path/to/custom/config.ini
python -m merge_pacs_metrics_prometheus_exporter start
```

## Contributing

Please read [CONTRIBUTING.md](https://gist.github.com/PurpleBooth/b24679402957c63ec426) for details on our code of conduct, and the process for submitting pull requests to us.

## Authors

* **Benjamin Exley** - *Initial work* - [bdexley](https://github.com/bdexley)
* **Harikrishna Chintalapudi** - *Ongoing Development*

See also the list of [contributors](https://github.com/your/project/contributors) who participated in this project.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details