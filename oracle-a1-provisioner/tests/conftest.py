import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest


@pytest.fixture
def settings():
    return SimpleNamespace(
        user_ocid="u", tenancy_ocid="t", fingerprint="f", private_key="-----BEGIN PRIVATE KEY-----\nx",
        private_key_passphrase=None, region="us-ashburn-1", compartment_ocid="c", availability_domain="AD-1",
        subnet_ocid="s", boot_volume_ocid="b", ssh_public_key="ssh-ed25519 key", dry_run=True,
        discord_webhook_url=None, state_bucket="bucket", object_storage_namespace="namespace",
        instance_name="servidor-bots", ocpus=1, memory_gbs=6, capacity_alerts=False)


@pytest.fixture
def resources():
    return SimpleNamespace(lifecycle_state="AVAILABLE", availability_domain="AD-1", compartment_id="c", image_id="image"), \
           SimpleNamespace(lifecycle_state="AVAILABLE", compartment_id="c", availability_domain=None)
