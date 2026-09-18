#!/usr/bin/env python3

import argparse
import os
import time
from pprint import pprint

import googleapiclient.discovery
import google.auth

credentials, project = google.auth.default()
service = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

#
# Stub code - just lists all instances
#
#!/usr/bin/env python3

import os
import time
import google.auth
import googleapiclient.discovery

# Authenticate and construct Compute Engine service client
credentials, project = google.auth.default()
compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

ZONE = 'us-west1-b'

# TODO: Replace with your actual Part 1 instance name if different
BASE_INSTANCE_NAME = 'flask-instance-1789674184'
SNAPSHOT_NAME = f"base-snapshot-{BASE_INSTANCE_NAME}"


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


def get_boot_disk_name(compute, project, zone, instance_name):
    """Retrieve the boot disk name of a given instance."""
    instance = compute.instances().get(
        project=project,
        zone=zone,
        instance=instance_name
    ).execute()

    for disk in instance.get('disks', []):
        if disk.get('boot', False):
            # 'source' has the full URL: projects/.../zones/.../disks/<disk-name>
            disk_url = disk['source']
            disk_name = disk_url.split('/')[-1]
            return disk_name

    raise RuntimeError(f"Could not find boot disk for instance {instance_name}")


def create_snapshot_from_disk(compute, project, zone, disk_name, snapshot_name):
    """Create a snapshot from a specified disk if it does not already exist."""
    # Check if snapshot already exists
    snapshots = compute.snapshots().list(project=project).execute()
    existing_snapshots = [s['name'] for s in snapshots.get('items', [])]
    if snapshot_name in existing_snapshots:
        print(f"Snapshot '{snapshot_name}' already exists. Skipping creation.")
        snapshot_url = compute.snapshots().get(project=project, snapshot=snapshot_name).execute()['selfLink']
        return snapshot_url

    print(f"Creating snapshot '{snapshot_name}' from disk '{disk_name}'...")
    snapshot_body = {
        'name': snapshot_name,
        'description': f"Snapshot taken from {disk_name}"
    }

    op = compute.disks().createSnapshot(
        project=project,
        zone=zone,
        disk=disk_name,
        body=snapshot_body
    ).execute()
    wait_for_zone_operation(compute, project, zone, op)
    print("Snapshot created successfully.")

    snapshot_info = compute.snapshots().get(project=project, snapshot=snapshot_name).execute()
    return snapshot_info['selfLink']


def create_instance_from_snapshot(compute, project, zone, instance_name, snapshot_link):
    """Create a new VM instance using the specified snapshot as its boot disk source."""
    machine_type = f"zones/{zone}/machineTypes/f1-micro"

    config = {
        'name': instance_name,
        'machineType': machine_type,
        'disks': [
            {
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceSnapshot': snapshot_link,
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
        }
    }

    print(f"Creating instance '{instance_name}' from snapshot...")
    start_time = time.perf_counter()

    op = compute.instances().insert(
        project=project,
        zone=zone,
        body=config
    ).execute()
    wait_for_zone_operation(compute, project, zone, op)

    elapsed_time = time.perf_counter() - start_time
    print(f"Instance '{instance_name}' created in {elapsed_time:.2f} seconds.")
    return elapsed_time


def main():
    print(f"1. Resolving boot disk for '{BASE_INSTANCE_NAME}'...")
    boot_disk_name = get_boot_disk_name(compute, project, ZONE, BASE_INSTANCE_NAME)
    print(f"Found boot disk: {boot_disk_name}")

    print(f"\n2. Creating base snapshot: {SNAPSHOT_NAME}...")
    snapshot_link = create_snapshot_from_disk(compute, project, ZONE, boot_disk_name, SNAPSHOT_NAME)

    print("\n3. Provisioning 3 cloned instances from snapshot...")
    timing_results = []

    for i in range(1, 4):
        clone_name = f"flask-clone-{i}-{int(time.time())}"
        duration = create_instance_from_snapshot(compute, project, ZONE, clone_name, snapshot_link)
        timing_results.append((clone_name, duration))

    # Write timing results to TIMING.md as required by the assignment
    timing_file_path = os.path.join(os.path.dirname(__file__), 'TIMING.md')
    with open(timing_file_path, 'w') as f:
        f.write("# Provisioning Timing Results\n\n")
        f.write("Time required to create instances from snapshot:\n\n")
        f.write("| Instance Name | Provisioning Time (seconds) |\n")
        f.write("| --- | --- |\n")
        for name, duration in timing_results:
            f.write(f"| {name} | {duration:.2f} s |\n")

    print(f"\nTiming results successfully saved to {timing_file_path}")


if __name__ == '__main__':
    main()