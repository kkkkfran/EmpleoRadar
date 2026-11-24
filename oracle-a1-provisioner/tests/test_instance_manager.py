from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from oracle_retry.instance_manager import InstanceManager
from oracle_retry.validators import ValidationError


def manager(settings, resources, state="RUNNING"):
    volume, subnet = resources
    compute = Mock()
    block, network, storage = Mock(), Mock(), Mock()
    block.get_boot_volume.return_value.data = volume
    network.get_subnet.return_value.data = subnet
    compute.list_shapes.return_value.data = [SimpleNamespace(shape="VM.Standard.A1.Flex")]
    compute.list_instances.return_value.data = []
    compute.list_instances.return_value.headers = {}
    compute.list_boot_volume_attachments.return_value.data = []
    compute.list_boot_volume_attachments.return_value.headers = {}
    compute.list_vnic_attachments.return_value.data = []
    compute.list_vnic_attachments.return_value.headers = {}
    if state in {"EXISTING", "STOPPED", "PROVISIONING"}:
        lifecycle = {"EXISTING": "RUNNING", "STOPPED": "STOPPED", "PROVISIONING": "PROVISIONING"}[state]
        compute.list_instances.return_value.data = [SimpleNamespace(id="i", display_name="servidor-bots", freeform_tags={}, lifecycle_state=lifecycle)]
    return InstanceManager(settings, compute, block, network, storage), compute, storage


def test_dry_run_does_not_launch(settings, resources):
    manager_, compute, _ = manager(settings, resources)
    assert manager_.run() == "dry_run"
    compute.launch_instance.assert_not_called()


def test_existing_instance_suppresses_launch(settings, resources):
    manager_, compute, _ = manager(settings, resources, "EXISTING")
    assert manager_.run() == "running"
    compute.launch_instance.assert_not_called()


def test_missing_volume_stops(settings, resources):
    volume, subnet = resources
    volume.lifecycle_state = "TERMINATED"
    manager_, _, _ = manager(settings, (volume, subnet))
    with pytest.raises(ValidationError, match="AVAILABLE"):
        manager_.run()


def test_volume_attached_stops(settings, resources):
    manager_, compute, _ = manager(settings, resources)
    compute.list_boot_volume_attachments.return_value.data = [SimpleNamespace(boot_volume_id="b", lifecycle_state="ATTACHED", instance_id="x")]
    with pytest.raises(ValidationError, match="conectado"):
        manager_.run()


def test_provisioning_instance_suppresses_launch(settings, resources):
    manager_, compute, _ = manager(settings, resources, "PROVISIONING")
    assert manager_.run() == "existing"
    compute.launch_instance.assert_not_called()


def test_incompatible_image_stops(settings, resources):
    manager_, compute, _ = manager(settings, resources)
    compute.list_shapes.return_value.data = []
    with pytest.raises(ValidationError, match="compatible"):
        manager_.run()


def test_stopped_instance_suppresses_launch(settings, resources):
    manager_, compute, _ = manager(settings, resources, "STOPPED")
    assert manager_.run() == "existing"
    compute.launch_instance.assert_not_called()
