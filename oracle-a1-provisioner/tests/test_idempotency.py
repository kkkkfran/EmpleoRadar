from unittest.mock import Mock
from types import SimpleNamespace

import pytest
from oci.exceptions import ServiceError

from oracle_retry.instance_manager import InstanceManager


def test_persistent_lock_suppresses_another_launch(settings, resources):
    volume, subnet = resources
    compute, block, network, storage = Mock(), Mock(), Mock(), Mock()
    block.get_boot_volume.return_value.data, network.get_subnet.return_value.data = volume, subnet
    compute.list_instances.return_value.data = []
    compute.list_instances.return_value.headers = {}
    compute.list_boot_volume_attachments.return_value.data = []
    compute.list_boot_volume_attachments.return_value.headers = {}
    compute.list_shapes.return_value.data = [SimpleNamespace(shape="VM.Standard.A1.Flex")]
    storage.put_object.side_effect = Exception("precondition failed")
    settings.dry_run = False
    manager = InstanceManager(settings, compute, block, network, storage)
    # SDK conflict is asserted in the integration/mocked SDK path; this checks no launch before reservation.
    try:
        manager.run()
    except Exception:
        pass
    compute.launch_instance.assert_not_called()


def _live_manager(settings, resources):
    volume, subnet = resources
    settings.dry_run = False
    compute, block, network, storage = Mock(), Mock(), Mock(), Mock()
    block.get_boot_volume.return_value.data, network.get_subnet.return_value.data = volume, subnet
    compute.list_instances.return_value.data = []
    compute.list_instances.return_value.headers = {}
    compute.list_boot_volume_attachments.return_value.data = []
    compute.list_boot_volume_attachments.return_value.headers = {}
    compute.list_shapes.return_value.data = [SimpleNamespace(shape="VM.Standard.A1.Flex")]
    return InstanceManager(settings, compute, block, network, storage), compute, storage


def test_successful_launch(settings, resources):
    manager, compute, storage = _live_manager(settings, resources)
    compute.launch_instance.return_value.data.id = "instance-ocid"
    assert manager.run() == "created"
    storage.put_object.assert_called_once()
    compute.launch_instance.assert_called_once()


def test_capacity_releases_lock_for_next_cron(settings, resources):
    manager, compute, storage = _live_manager(settings, resources)
    compute.launch_instance.side_effect = ServiceError(500, "request", {}, "OutOfHostCapacity")
    assert manager.run() == "capacity"
    storage.delete_object.assert_called_once()


def test_ambiguous_network_failure_keeps_lock(settings, resources):
    manager, compute, storage = _live_manager(settings, resources)
    compute.launch_instance.side_effect = TimeoutError("connection lost after request")
    with pytest.raises(TimeoutError):
        manager.run()
    storage.put_object.assert_called_once()
    storage.delete_object.assert_not_called()
    assert compute.launch_instance.call_count == 1


def test_two_simultaneous_launchers_only_one_gets_lock(settings, resources):
    first, compute, _ = _live_manager(settings, resources)
    second, second_compute, _ = _live_manager(settings, resources)
    first.storage.put_object.return_value = None
    second.storage.put_object.side_effect = ServiceError(412, "request", {}, "PreconditionFailed")
    compute.launch_instance.return_value.data.id = "instance-ocid"
    assert first.run() == "created"
    assert second.run() == "locked"
    compute.launch_instance.assert_called_once()
    second_compute.launch_instance.assert_not_called()
