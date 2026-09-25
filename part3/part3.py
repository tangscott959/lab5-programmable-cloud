#!/usr/bin/env python3

import os
import time
import json

# ==============================================================================
# DIFFERENCE 1: IMPORT MODERN CLOUD CLIENT LIBRARY
# Legacy (Discovery):
#   from googleapiclient import discovery
# Modern (Cloud Client Library for Extra Credit):
#   from google.cloud import compute_v1 (google-cloud-compute package)
# ==============================================================================
from google.cloud import compute_v1

CREDENTIALS_FILE = 'service-credentials.json'
ZONE = 'us-west1-c'

# Set authentication credentials and load project ID
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_FILE
with open(CREDENTIALS_FILE, 'r') as f:
    project = json.load(f)['project_id']

# Initialize typed clients
instances_client = compute_v1.InstancesClient()
images_client = compute_v1.ImagesClient()

# Startup script to be executed on VM-2 (Flask app setup)
VM2_STARTUP_SCRIPT = """#!/bin/bash
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

# Startup script executed by VM-1 upon booting
# It installs google-cloud-compute, fetches payload from metadata, and triggers vm1_launch_vm2.py
VM1_STARTUP_SCRIPT = """#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-pip curl

# Install Cloud Client Library on VM-1
pip3 install google-cloud-compute

mkdir -p /srv
cd /srv

# Download embedded metadata files from Google link-local metadata server
curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/service-credentials > service-credentials.json
curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/vm1-launch-vm2-code > vm1_launch_vm2.py
curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/vm2-startup-script > vm2-startup-script.sh

chmod +x vm1_launch_vm2.py

# Execute VM-2 provisioner script
python3 /srv/vm1_launch_vm2.py > /var/log/vm1_launch_vm2.log 2>&1
"""

def create_vm1(project_id, zone):
    """Deploy VM-1 and provide required credentials and provisioner code via Metadata."""
    instance_name = f"launching-vm1-{int(time.time())}"

    # Read credentials file content to inject into metadata
    with open(CREDENTIALS_FILE, 'r') as f:
        credentials_content = f.read()

    # Read vm1_launch_vm2.py code to inject into metadata
    with open('vm1_launch_vm2.py', 'r') as f:
        launch_vm2_content = f.read()

    # Query latest Ubuntu 22.04 LTS image
    image = images_client.get_from_family(project="ubuntu-os-cloud", family="ubuntu-2204-lts")

    boot_disk = compute_v1.AttachedDisk(
        boot=True,
        auto_delete=True,
        initialize_params=compute_v1.AttachedDiskInitializeParams(
            source_image=image.self_link
        )
    )

    access_config = compute_v1.AccessConfig(
        type_=compute_v1.AccessConfig.Type.ONE_TO_ONE_NAT.name,
        name="External NAT"
    )
    network_interface = compute_v1.NetworkInterface(
        network=f"projects/{project_id}/global/networks/default",
        access_configs=[access_config]
    )

    # Pack startup script, service credentials, provisioner code, and VM-2 startup script into metadata items
    metadata = compute_v1.Metadata(
        items=[
            compute_v1.Items(key="startup-script", value=VM1_STARTUP_SCRIPT),
            compute_v1.Items(key="service-credentials", value=credentials_content),
            compute_v1.Items(key="vm1-launch-vm2-code", value=launch_vm2_content),
            compute_v1.Items(key="vm2-startup-script", value=VM2_STARTUP_SCRIPT),
        ]
    )

    instance_resource = compute_v1.Instance(
        name=instance_name,
        machine_type=f"zones/{zone}/machineTypes/f1-micro",
        disks=[boot_disk],
        network_interfaces=[network_interface],
        metadata=metadata
    )

    print(f"Creating VM-1 ('{instance_name}') in zone '{zone}' using Cloud Client Libraries...")

    # Wait for VM-1 creation to complete
    operation = instances_client.insert(
        project=project_id,
        zone=zone,
        instance_resource=instance_resource
    )
    operation.result()
    print(f"VM-1 ('{instance_name}') created successfully.")

    instance = instances_client.get(project=project_id, zone=zone, instance=instance_name)
    external_ip = instance.network_interfaces[0].access_configs[0].nat_i_p
    print(f"VM-1 External IP: {external_ip}")
    print("VM-1 is now installing dependencies and triggering VM-2 creation...")
    return instance_name

def list_instances(project_id, zone):
    """List all instances in the specified zone."""
    print(f"\nCurrent instances in zone '{zone}':")
    instance_list = instances_client.list(project=project_id, zone=zone)
    for inst in instance_list:
        ip = inst.network_interfaces[0].access_configs[0].nat_i_p if inst.network_interfaces[0].access_configs else "None"
        print(f" - {inst.name} | Status: {inst.status} | External IP: {ip}")

def main():
    print(f"Using Project: {project}")
    create_vm1(project, ZONE)
    list_instances(project, ZONE)

if __name__ == '__main__':
    main()