#!/usr/bin/env python3
import time
import os
import googleapiclient.discovery
import google.oauth2.service_account as service_account

ZONE = 'us-west1-b'
CREDENTIALS_FILE = 'service-credentials.json'

credentials = service_account.Credentials.from_service_account_file(filename=CREDENTIALS_FILE)
# Read project_id directly from credentials to avoid environment variable dependencies
project = credentials.project_id
compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

def wait_for_zone_operation(compute, project, zone, operation):
    """Wait for a zone-level asynchronous operation to complete."""
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

def main():
    # Read the Flask startup script injected for VM-2
    with open('vm2-startup-script.sh', 'r') as f:
        vm2_startup_script = f.read()

    vm2_name = f"flask-vm2-{int(time.time())}"
    image_response = compute.images().getFromFamily(
        project='ubuntu-os-cloud',
        family='ubuntu-2204-lts'
    ).execute()
    source_disk_image = image_response['selfLink']

    config = {
        'name': vm2_name,
        'machineType': f"zones/{ZONE}/machineTypes/f1-micro",
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
        'tags': {
            'items': ['allow-5000']
        },
        'metadata': {
            'items': [
                {
                    'key': 'startup-script',
                    'value': vm2_startup_script
                }
            ]
        }
    }

    print(f"VM-1 launching VM-2: {vm2_name}...")
    op = compute.instances().insert(
        project=project,
        zone=ZONE,
        body=config
    ).execute()
    wait_for_zone_operation(compute, project, ZONE, op)
    print("VM-2 created successfully from VM-1.")

if __name__ == '__main__':
    main()