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

# Configure credentials and extract project ID
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_FILE
with open(CREDENTIALS_FILE, 'r') as f:
    project = json.load(f)['project_id']

# ==============================================================================
# DIFFERENCE 2: SPECIALIZED CLIENT INITIALIZATION
# Legacy:
#   service = discovery.build('compute', 'v1', credentials=credentials)
# Modern:
#   Directly instantiate typed client classes
# ==============================================================================
instances_client = compute_v1.InstancesClient()
images_client = compute_v1.ImagesClient()

# Read the startup script intended for VM-2 from the local filesystem
with open('vm2-startup-script.sh', 'r') as f:
    vm2_startup_script = f.read()

def create_vm2(project_id, zone):
    """Launch VM-2 directly from within VM-1 using Cloud Client Libraries."""
    instance_name = f"flask-vm2-{int(time.time())}"

    # Query latest Ubuntu 22.04 LTS image
    image = images_client.get_from_family(project="ubuntu-os-cloud", family="ubuntu-2204-lts")

    # Configure boot disk
    boot_disk = compute_v1.AttachedDisk(
        boot=True,
        auto_delete=True,
        initialize_params=compute_v1.AttachedDiskInitializeParams(
            source_image=image.self_link
        )
    )

    # Configure network interface with external NAT IP
    access_config = compute_v1.AccessConfig(
        type_=compute_v1.AccessConfig.Type.ONE_TO_ONE_NAT.name,
        name="External NAT"
    )
    network_interface = compute_v1.NetworkInterface(
        network=f"projects/{project_id}/global/networks/default",
        access_configs=[access_config]
    )

    # Inject VM-2 startup script and firewall network tag
    metadata = compute_v1.Metadata(
        items=[compute_v1.Items(key="startup-script", value=vm2_startup_script)]
    )
    tags = compute_v1.Tags(items=["allow-5000"])

    # Assemble instance resource object
    instance_resource = compute_v1.Instance(
        name=instance_name,
        machine_type=f"zones/{zone}/machineTypes/f1-micro",
        disks=[boot_disk],
        network_interfaces=[network_interface],
        tags=tags,
        metadata=metadata
    )

    print(f"[VM-1] Launching '{instance_name}' in zone '{zone}' using Cloud Client Libraries...")

    # ==========================================================================
    # DIFFERENCE 3: AUTOMATIC OPERATION WAITING
    # Legacy:
    #   op = compute.instances().insert(...).execute() with manual while loop
    # Modern:
    #   operation = instances_client.insert(...)
    #   operation.result() automatically blocks until complete
    # ==========================================================================
    operation = instances_client.insert(
        project=project_id,
        zone=zone,
        instance_resource=instance_resource
    )
    operation.result()
    print(f"[VM-1] '{instance_name}' created successfully.")

    # Retrieve and print external IP
    instance = instances_client.get(project=project_id, zone=zone, instance=instance_name)
    external_ip = instance.network_interfaces[0].access_configs[0].nat_i_p
    print(f"[VM-1] VM-2 External IP: {external_ip}")
    print(f"[VM-1] Flask accessible at: http://{external_ip}:5000")

if __name__ == '__main__':
    create_vm2(project, ZONE)