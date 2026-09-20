#!/usr/bin/env python3

import os
import time
import googleapiclient.discovery
import google.oauth2.service_account as service_account

CREDENTIALS_FILE = 'service-credentials.json'
ZONE = 'us-west1-b'

# 1. Authenticate and extract project ID from the service account credentials
credentials = service_account.Credentials.from_service_account_file(filename=CREDENTIALS_FILE)
project = credentials.project_id
service = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

def wait_for_zone_operation(compute, project, zone, operation):
    """Wait for a zone-level asynchronous operation to complete."""
    print(f"Waiting for zone operation {operation['name']} to finish...")
    while True:
        result = compute.zoneOperations().get(
            project=project,
            zone=zone,
            operation=operation['name']
        ).execute()

        if result.get('status') == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return result
        time.sleep(2)

# Startup script to configure and launch the Flask application on VM-2
FLASK_STARTUP_SCRIPT = """#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-pip git
pip3 install flask gitpython

mkdir -p /srv
cd /srv
if [ ! -d "flask-tutorial" ]; then
    git clone https://github.com/pallets/flask.git flask-repo
    cp -r flask-repo/examples/tutorial flask-tutorial
fi

cd /srv/flask-tutorial
pip3 install -e .
export FLASK_APP=flaskr
flask init-db
nohup flask run --host=0.0.0.0 --port=5000 > /var/log/flask.log 2>&1 &
"""

# Shell script executed upon VM-1 startup
VM1_SHELL_STARTUP = """#!/bin/bash
set -e
mkdir -p /srv
cd /srv

# Fetch injected files from link-local metadata
curl -f http://metadata.google.internal/computeMetadata/v1/instance/attributes/vm2-startup-script -H "Metadata-Flavor: Google" > vm2-startup-script.sh
curl -f http://metadata.google.internal/computeMetadata/v1/instance/attributes/service-credentials -H "Metadata-Flavor: Google" > service-credentials.json
curl -f http://metadata.google.internal/computeMetadata/v1/instance/attributes/vm1-launch-code -H "Metadata-Flavor: Google" > vm1_launch_vm2.py

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-pip

pip3 install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib uritemplate

python3 ./vm1_launch_vm2.py
"""

def create_vm1(compute, project, zone):
    """Create launcher VM-1 with metadata containing credentials and scripts to launch VM-2."""
    vm1_name = f"launching-vm1-{int(time.time())}"

    # Read local service credentials and launcher code contents
    with open(CREDENTIALS_FILE, 'r') as f:
        credentials_content = f.read()

    with open('vm1_launch_vm2.py', 'r') as f:
        vm1_launch_code_content = f.read()

    image_response = compute.images().getFromFamily(
        project='ubuntu-os-cloud',
        family='ubuntu-2204-lts'
    ).execute()
    source_disk_image = image_response['selfLink']

    config = {
        'name': vm1_name,
        'machineType': f"zones/{zone}/machineTypes/f1-micro",
        'disks': [
            {
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceImage': source_disk_image,
                }
            }
        ],
        'networkInterfaces': [{
            'network': f"projects/{project}/global/networks/default",
            'accessConfigs': [
                {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
            ]
        }],
        'metadata': {
            'items': [
                {'key': 'startup-script', 'value': VM1_SHELL_STARTUP},
                {'key': 'vm2-startup-script', 'value': FLASK_STARTUP_SCRIPT},
                {'key': 'service-credentials', 'value': credentials_content},
                {'key': 'vm1-launch-code', 'value': vm1_launch_code_content}
            ]
        }
    }

    print(f"Creating launcher VM-1: '{vm1_name}'...")
    op = compute.instances().insert(
        project=project,
        zone=zone,
        body=config
    ).execute()
    wait_for_zone_operation(compute, project, zone, op)
    print(f"Launcher VM-1 '{vm1_name}' created.")
    return vm1_name

def main():
    print(f"Using project: {project}")
    vm1_name = create_vm1(service, project, ZONE)
    print("\nVM-1 has been started. It will now fetch metadata and create VM-2 in the background.")
    print("You can verify VM-2's appearance using: gcloud compute instances list")

if __name__ == '__main__':
    main()