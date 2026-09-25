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

# Source instance name from Part 1
SOURCE_INSTANCE_NAME = 'flask-instance-1790311357'
SNAPSHOT_NAME = f"base-snapshot-{SOURCE_INSTANCE_NAME}"

# Authentication setup using standard environment variable
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_FILE
with open(CREDENTIALS_FILE, 'r') as f:
    project = json.load(f)['project_id']

# ==============================================================================
# DIFFERENCE 2: SPECIALIZED CLIENT INSTANTIATION
# Legacy:
#   service = discovery.build('compute', 'v1', credentials=credentials)
# Modern:
#   Directly instantiate targeted client classes:
#   - compute_v1.InstancesClient()
#   - compute_v1.DisksClient()
#   - compute_v1.SnapshotsClient()
# ==============================================================================
instances_client = compute_v1.InstancesClient()
disks_client = compute_v1.DisksClient()
snapshots_client = compute_v1.SnapshotsClient()

def get_boot_disk_name(project_id, zone, instance_name):
    """Retrieve the boot disk name associated with the source instance."""
    # ==========================================================================
    # DIFFERENCE 3: GET INSTANCE DETAILS
    # Legacy:
    #   instance = compute.instances().get(project=..., zone=..., instance=...).execute()
    #   Check instance['disks'] dictionary keys
    # Modern:
    #   instance = instances_client.get(project=..., zone=..., instance=...)
    #   Access strongly typed attributes: instance.disks[...].boot and .source
    # ==========================================================================
    instance = instances_client.get(project=project_id, zone=zone, instance=instance_name)
    for disk in instance.disks:
        if disk.boot:
            return disk.source.split('/')[-1]
    raise RuntimeError(f"No boot disk found on instance {instance_name}")

def create_snapshot_from_disk(project_id, zone, disk_name, snapshot_name):
    """Create a persistent disk snapshot using the Cloud Client DisksClient."""
    try:
        existing = snapshots_client.get(project=project_id, snapshot=snapshot_name)
        if existing:
            print(f"Snapshot '{snapshot_name}' already exists. Skipping creation.")
            return existing.self_link
    except Exception:
        pass

    # ==========================================================================
    # DIFFERENCE 4: SNAPSHOT RESOURCE CONFIGURATION
    # Legacy:
    #   Pass raw dict: body={'name': snapshot_name, 'description': ...}
    # Modern:
    #   Instantiate typed Protobuf object compute_v1.Snapshot(...)
    # ==========================================================================
    snapshot_resource = compute_v1.Snapshot(
        name=snapshot_name,
        description=f"Snapshot created from disk {disk_name}"
    )

    print(f"Creating snapshot '{snapshot_name}' from disk '{disk_name}'...")
    
    # ==========================================================================
    # DIFFERENCE 5: SNAPSHOT CREATION & AUTOMATIC OPERATION POLLING
    # Legacy:
    #   op = compute.disks().createSnapshot(project=..., zone=..., disk=..., body=...).execute()
    #   Manual while loop polling zoneOperations / globalOperations
    # Modern:
    #   operation = disks_client.create_snapshot(project=..., zone=..., disk=..., snapshot_resource=...)
    #   operation.result() automatically blocks until the snapshot is ready
    # ==========================================================================
    operation = disks_client.create_snapshot(
        project=project_id,
        zone=zone,
        disk=disk_name,
        snapshot_resource=snapshot_resource
    )
    operation.result()  # Blocks until snapshot is completed
    print(f"Snapshot '{snapshot_name}' created successfully.")

    snapshot = snapshots_client.get(project=project_id, snapshot=snapshot_name)
    return snapshot.self_link

def create_instance_from_snapshot(project_id, zone, instance_name, snapshot_link):
    """Create a new Compute Engine instance using a disk snapshot."""
    # ==========================================================================
    # DIFFERENCE 6: SPECIFYING SNAPSHOT AS BOOT DISK SOURCE
    # Legacy:
    #   Dictionary: 'initializeParams': {'sourceSnapshot': snapshot_link}
    # Modern:
    #   Protobuf field: compute_v1.AttachedDiskInitializeParams(source_snapshot=snapshot_link)
    # ==========================================================================
    boot_disk = compute_v1.AttachedDisk(
        boot=True,
        auto_delete=True,
        initialize_params=compute_v1.AttachedDiskInitializeParams(
            source_snapshot=snapshot_link
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

    tags = compute_v1.Tags(items=["allow-5000"])

    # Startup script only needs to start the already existing application
    startup_script = """#!/bin/bash
cd /srv/flask-tutorial
export FLASK_APP=flaskr
nohup flask run --host=0.0.0.0 --port=5000 > /var/log/flask.log 2>&1 &
"""
    metadata = compute_v1.Metadata(
        items=[compute_v1.Items(key="startup-script", value=startup_script)]
    )

    instance_resource = compute_v1.Instance(
        name=instance_name,
        machine_type=f"zones/{zone}/machineTypes/f1-micro",
        disks=[boot_disk],
        network_interfaces=[network_interface],
        tags=tags,
        metadata=metadata
    )

    print(f"Creating instance '{instance_name}' from snapshot...")
    start_time = time.time()

    # ==========================================================================
    # DIFFERENCE 7: INSTANCE CREATION AND TIMING BENCHMARK
    # Legacy:
    #   compute.instances().insert(...).execute() with custom polling loop
    # Modern:
    #   instances_client.insert(...).result() blocks accurately until provisioned
    # ==========================================================================
    operation = instances_client.insert(
        project=project_id,
        zone=zone,
        instance_resource=instance_resource
    )
    operation.result()  # Blocks until the instance is fully provisioned

    elapsed_time = time.time() - start_time
    print(f"Instance '{instance_name}' created in {elapsed_time:.2f} seconds.")

    # Retrieve assigned external IP address
    inst = instances_client.get(project=project_id, zone=zone, instance=instance_name)
    external_ip = inst.network_interfaces[0].access_configs[0].nat_i_p
    print(f"Instance '{instance_name}' IP: {external_ip} | http://{external_ip}:5000")

    return elapsed_time

def main():
    print(f"Project: {project}")
    print(f"Source Instance: {SOURCE_INSTANCE_NAME}")

    # 1. Retrieve the source instance boot disk and snapshot it
    boot_disk_name = get_boot_disk_name(project, ZONE, SOURCE_INSTANCE_NAME)
    snapshot_link = create_snapshot_from_disk(project, ZONE, boot_disk_name, SNAPSHOT_NAME)

    # 2. Sequentially launch 3 instances and measure individual creation durations
    timing_records = []
    base_name = f"clone-{int(time.time())}"

    for i in range(1, 4):
        inst_name = f"{base_name}-{i}"
        duration = create_instance_from_snapshot(project, ZONE, inst_name, snapshot_link)
        timing_records.append((inst_name, duration))

    # 3. Output results into TIMING.md
    with open("TIMING.md", "w") as f:
        f.write("# Instance Creation Timings (From Snapshot)\n\n")
        f.write("| Instance Name | Creation Time (seconds) |\n")
        f.write("|---|---|\n")
        for name, duration in timing_records:
            f.write(f"| {name} | {duration:.2f} |\n")

    print("\nBenchmark completed. Timings recorded to TIMING.md.")

if __name__ == '__main__':
    main()