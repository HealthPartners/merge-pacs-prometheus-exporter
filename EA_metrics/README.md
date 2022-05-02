# Metrics collection from the Enterprise Archive Peers

## Purpose
This script ones on the EA servers, from the elb servers, specifically, in a clustered environment. It will collect a few different types of metric data and host them on a local http server using the prometheus_client package.

## Prerequisites:
1.  Test if pip is installed with 'python -m pip --version'. If not, install pip:

     ```curl -sSL https://bootstrap.pypa.io/pip/2.7/get-pip.py --insecure -o get-pip.py```
     ```python get-pip.py --trusted-host pypi.org --trusted-host files.pythonhosted.org```

1. The paramiko package must be installed with 'python -m pip --trusted-host pypi.org --trusted-host files.pythonhosted.org install paramiko'
1. The prometheus_client package must be installed with 'python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org prometheus_client'
1. You MUST be able to SSH from the initial server (elb01 or elb02) to ALL other servers in the peer without requiring a password. You can do with with shared SSH keys. From both elb servers, do:

     ```ssh-keygen -t rsa -b 2048```

1. Then on each elb, execute this command for each server in the peer (including BOTH elb servers, even the one you're on)

     ```ssh-copy-id servername```

## Deployment
- Copy all files from this repository to ~/hpmetrics on each EA peer, updating any that are already there with the new versions
- Give permissions to allow run_metrics.sh to be executed if it is newly created:

     ```chmod u+x ~/hpmetrics/run_metrics.sh```

## Running the metrics collection
- On each peer, start the script with

     ```~/hpmetrics/run_metrics.sh```

**NOTE:** This is written for Python 2.7 which is what's on the EAs.
{: .note}
