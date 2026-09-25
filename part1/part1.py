#!/usr/bin/env python3

import os
import time
import json

# ==============================================================================
# DIFFERENCE 1: IMPORT SOURCE AND LIBRARY PACKAGE
# Legacy (Discovery):
#   from googleapiclient import discovery
#   from google.oauth2 import service_account
# Modern (Cloud Client Library for Extra Credit):
#   from google.cloud import compute_v1 (google-cloud-compute package)
# ==============================================================================
from google.cloud import compute_v1

CREDENTIALS_FILE = 'service-credentials.json'
ZONE = 'us-west1-b'

# Set environment variable for authentication and load project ID
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_FILE
with open(CREDENTIALS_FILE, 'r') as f:
    project = json.load(f)['project_id']

# ==============================================================================
# DIFFERENCE 2: CLIENT INITIALIZATION MECHANISM
# Legacy:
#   service = discovery.build('compute', 'v1', credentials=credentials)
# Modern:
#   Directly instantiate typed client classes (InstancesClient, ImagesClient).
#   No dynamic Discovery schema downloading at runtime.
# ==============================================================================
instances_client = compute_v1.InstancesClient()
images_client = compute_v1.ImagesClient()

# Startup script to configure dependencies and run the Flask application
STARTUP_SCRIPT = """#!/bin/bash
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

def create_instance(project_id, zone):
    """Create a Compute Engine instance configured with a startup script using Cloud Client Libraries."""
    instance_name = f"flask-instance-{int(time.time())}"

    # ==========================================================================
    # DIFFERENCE 3: IMAGE LOOKUP METHOD
    # Legacy:
    #   compute.images().getFromFamily(project=..., family=...).execute()
    # Modern:
    #   images_client.get_from_family(project=..., family=...)
    # ==========================================================================
    image = images_client.get_from_family(project="ubuntu-os-cloud", family="ubuntu-2204-lts")

    # ==========================================================================
    # DIFFERENCE 4: RESOURCE DEFINITION USING PROTOBUF CLASSES INSTEAD OF RAW DICTS
    # Legacy:
    #   Constructed via nested native dict: {'disks': [...], 'networkInterfaces': [...]}
    # Modern:
    #   Constructed using typed Protobuf objects with strict attribute schema:
    #   compute_v1.AttachedDisk, compute_v1.NetworkInterface, compute_v1.Instance
    # ==========================================================================
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

    metadata = compute_v1.Metadata(
        items=[compute_v1.Items(key="startup-script", value=STARTUP_SCRIPT)]
    )
    tags = compute_v1.Tags(items=["allow-5000"])

    instance_resource = compute_v1.Instance(
        name=instance_name,
        machine_type=f"zones/{zone}/machineTypes/f1-micro",
        disks=[boot_disk],
        network_interfaces=[network_interface],
        tags=tags,
        metadata=metadata
    )

    print(f"Creating instance '{instance_name}' in zone '{zone}' using Cloud Client Library...")

    # ==========================================================================
    # DIFFERENCE 5: LONG-RUNNING OPERATION POLLING
    # Legacy:
    #   op = compute.instances().insert(...).execute()
    #   Manual while True polling loop on compute.zoneOperations().get(...)
    # Modern:
    #   operation = instances_client.insert(...)
    #   operation.result() automatically polls until completion.
    # ==========================================================================
    operation = instances_client.insert(
        project=project_id,
        zone=zone,
        instance_resource=instance_resource
    )
    operation.result()  # Blocks and waits automatically until ready
    print(f"Instance '{instance_name}' created successfully.")

    # ==========================================================================
    # DIFFERENCE 6: RESOURCE ATTRIBUTE ACCESS
    # Legacy:
    #   instance['networkInterfaces'][0]['accessConfigs'][0]['natIP'] (Dict lookup)
    # Modern:
    #   instance.network_interfaces[0].access_configs[0].nat_i_p (Object attribute)
    # ==========================================================================
    instance = instances_client.get(project=project_id, zone=zone, instance=instance_name)
    external_ip = instance.network_interfaces[0].access_configs[0].nat_i_p
    print(f"External IP: {external_ip}")
    print(f"Flask will be accessible at: http://{external_ip}:5000")
    return instance_name

def list_instances(project_id, zone):
    """List all instances in the specified zone using Cloud Client Libraries."""
    print(f"\nListing instances in project '{project_id}', zone '{zone}':")
    # ==========================================================================
    # DIFFERENCE 7: LIST ITERATION MECHANISM
    # Legacy:
    #   result = compute.instances().list(...).execute()
    #   items = result.get('items', [])
    # Modern:
    #   Directly returns a typed, auto-paginating iterable of Instance objects.
    # ==========================================================================
    instance_list = instances_client.list(project=project_id, zone=zone)
    for inst in instance_list:
        ip = inst.network_interfaces[0].access_configs[0].nat_i_p if inst.network_interfaces[0].access_configs else "None"
        print(f" - {inst.name} | Status: {inst.status} | External IP: {ip}")

def main():
    print(f"Using Project: {project}")
    create_instance(project, ZONE)
    list_instances(project, ZONE)

if __name__ == '__main__':
    main()