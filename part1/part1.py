#!/usr/bin/env python3

import os
import time
import google.auth
import googleapiclient.discovery

# Authenticate and construct Compute Engine service client
credentials, project = google.auth.default()
service = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

ZONE = 'us-west1-b'
INSTANCE_NAME = f"flask-instance-{int(time.time())}"
FIREWALL_RULE_NAME = 'allow-5000'
TAG_NAME = 'allow-5000'


def list_instances(compute, project, zone):
    """List all instances in a given zone (from starter stub)."""
    result = compute.instances().list(project=project, zone=zone).execute()
    return result['items'] if 'items' in result else []


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


def wait_for_global_operation(compute, project, operation):
    """Wait for a global-level asynchronous operation to complete."""
    print(f"Waiting for global operation {operation['name']} to finish...")
    while True:
        result = compute.globalOperations().get(
            project=project,
            operation=operation['name']
        ).execute()

        if result.get('status') == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return result
        time.sleep(2)


def ensure_firewall_rule(compute, project):
    """Check if 'allow-5000' exists; create it if missing."""
    firewalls = compute.firewalls().list(project=project).execute()
    rules = [rule['name'] for rule in firewalls.get('items', [])]

    if FIREWALL_RULE_NAME in rules:
        print(f"Firewall rule '{FIREWALL_RULE_NAME}' already exists.")
        return

    print(f"Creating firewall rule '{FIREWALL_RULE_NAME}'...")
    firewall_body = {
        "name": FIREWALL_RULE_NAME,
        "description": "Allow TCP port 5000 for instances tagged allow-5000",
        "network": f"projects/{project}/global/networks/default",
        "targetTags": [TAG_NAME],
        "sourceRanges": ["0.0.0.0/0"],
        "allowed": [
            {
                "IPProtocol": "tcp",
                "ports": ["5000"]
            }
        ]
    }

    op = compute.firewalls().insert(project=project, body=firewall_body).execute()
    wait_for_global_operation(compute, project, op)
    print("Firewall rule created successfully.")


def create_instance(compute, project, zone, name):
    """Create a VM instance with Ubuntu 22.04 LTS and a startup script."""
    image_response = compute.images().getFromFamily(
        project='ubuntu-os-cloud',
        family='ubuntu-2204-lts'
    ).execute()
    source_disk_image = image_response['selfLink']

    machine_type = f"zones/{zone}/machineTypes/f1-micro"

    startup_script = """#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y python3 python3-pip git

mkdir -p /opt/app
cd /opt/app

if [ ! -d "flask-tutorial" ]; then
    git clone https://github.com/cu-csci-4253-datacenter/flask-tutorial
fi

cd flask-tutorial
python3 setup.py install
pip3 install -e .

export FLASK_APP=flaskr
flask init-db
nohup flask run -h 0.0.0.0 --port 5000 > /var/log/flask.log 2>&1 &
"""

    config = {
        'name': name,
        'machineType': machine_type,
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
            'items': [{
                'key': 'startup-script',
                'value': startup_script
            }]
        }
    }

    print(f"Creating instance '{name}' in zone {zone}...")
    op = compute.instances().insert(project=project, zone=zone, body=config).execute()
    wait_for_zone_operation(compute, project, zone, op)
    print("Instance created successfully.")


def apply_network_tags(compute, project, zone, name, tag):
    """Apply network tags to the VM using instances.setTags."""
    print(f"Setting network tag '{tag}' on instance '{name}'...")
    instance = compute.instances().get(project=project, zone=zone, instance=name).execute()
    fingerprint = instance['tags']['fingerprint']
    existing_tags = instance['tags'].get('items', [])

    if tag not in existing_tags:
        existing_tags.append(tag)

    tags_body = {
        'items': existing_tags,
        'fingerprint': fingerprint
    }

    op = compute.instances().setTags(
        project=project,
        zone=zone,
        instance=name,
        body=tags_body
    ).execute()
    wait_for_zone_operation(compute, project, zone, op)
    print("Tag applied successfully.")


def get_external_ip(compute, project, zone, name):
    """Retrieve external NAT IP address of the instance."""
    instance = compute.instances().get(project=project, zone=zone, instance=name).execute()
    interfaces = instance.get('networkInterfaces', [])
    if interfaces:
        access_configs = interfaces[0].get('accessConfigs', [])
        if access_configs:
            return access_configs[0].get('natIP')
    return None


def main():
    # Print existing instances using starter code logic
    print("Your running instances before provisioning:")
    instances = list_instances(service, project, ZONE)
    if instances:
        for inst in instances:
            print(f" - {inst['name']}")
    else:
        print(" (No instances running in this zone)")

    print("\n--- Provisioning Flask Service ---")
    # 1. Ensure firewall rule exists
    ensure_firewall_rule(service, project)

    # 2. Create the VM instance
    create_instance(service, project, ZONE, INSTANCE_NAME)

    # 3. Apply the allow-5000 tag
    apply_network_tags(service, project, ZONE, INSTANCE_NAME, TAG_NAME)

    # 4. Display the external URL
    external_ip = get_external_ip(service, project, ZONE, INSTANCE_NAME)

    print("\n" + "=" * 60)
    if external_ip:
        print("The Flask application is initializing and will be available at:")
        print(f"http://{external_ip}:5000")
        print("\nNote: It may take 1-3 minutes for the startup script to finish.")
    else:
        print("Failed to retrieve external IP address.")
    print("=" * 60)


if __name__ == '__main__':
    main()