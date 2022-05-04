## Purpose
This script ones on the EA servers, from the elb servers, specifically, in a clustered environment. It will collect a few different types of metric data and host them on a local http server using the prometheus_client package.

## Prerequisites:
1.  Test if pip is installed with `python -m pip --version`. If not, install pip:

     ```curl -sSL https://bootstrap.pypa.io/pip/2.7/get-pip.py --insecure -o get-pip.py```
     ```python get-pip.py --trusted-host pypi.org --trusted-host files.pythonhosted.org```

1. The python packages paramiko, prometheus_client, and requests must be installed. Assuming you're not running as root, they can be installed for the local user. Run the following to installed (and ignore our web filter's self-signed certificate):
     ```python -m pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --user paramiko prometheus_client requests```
1. Ideally, you can SSH from the initial server (elb01 or elb02) to ALL other servers in the peer without requiring a password. You can do with with shared SSH keys. If you do not set this up, you'll need to provide the username and password to use for SSH to the script (see the Deployment section). From both elb servers, do:

     ```ssh-keygen -t rsa -b 2048```

1. Then on each elb, execute this command for each server in the peer (including BOTH elb servers, even the one you're on)

     ```ssh-copy-id servername```

## Deployment
- Copy all files from this repository to `home/healthpartners/hpmetrics` on each EA peer, updating any that are already there with the new versions
- Give permissions to allow run_metrics.sh to be executed if it is newly created:

     ```chmod u+x ~/hpmetrics/run_metrics.sh```

### Providing usernames and passwords
To run correctly, this script will need credentials for two things: Connecting with SSH to other servers in the peer (unless you've set up shared keys) and logging in to the EA Web Admin page to get Scheduled Work Engine (SWE) queue size info. There are two choices to provide this information.

#### Setting Username and Password by Environment Variables
If defined, the script will use the values provided in 4 environment variables for the usernames and passwords to use for SSH and EA Web connections. The easiest way to ensure these environment variables are always set is to define them in your `~/.bashrc` file. You can add something like the following to the file:

```
##
## Configuration for HealthPartners metrics collection
##

# Define username and passwords to use when connecting to other servers in the
# with ssh
export SSH_USERNAME=healthpartners
export SSH_PASSWORD=sshpassword

# Define username and password to use to log in to EA Web to scrape the
# Scheduled Work Engine queue sizes
export EAWEB_USERNAME=merge
export EAWEB_PASSWORD=eawebpassword
```

#### Setting Username and Password at Runtime
If you do not define some or any environment variables for usernames or passwords the `run_metrics.sh` script will prompt you to enter any missing ones. You don't have to enter values for the SSH credentials if you're using shared keys. But if you don't provide values for EA Web login the script will almost certainly fail to collect SWE metrics.

## Running the metrics collection
- On each peer, start the script with

     ```~/hpmetrics/run_metrics.sh```


**NOTE:** This is written for Python 2.7 which is what's on the EAs.
{: .note}
