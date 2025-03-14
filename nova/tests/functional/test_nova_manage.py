#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import collections
import datetime
from io import StringIO
import os.path
from unittest import mock

import fixtures
from neutronclient.common import exceptions as neutron_client_exc
import os_resource_classes as orc
from oslo_db import exception as oslo_db_exc
from oslo_serialization import jsonutils
from oslo_utils.fixture import uuidsentinel as uuids
from oslo_utils import timeutils

from nova.cmd import manage
from nova.compute import instance_list as list_instances
from nova import config
from nova import context
from nova import exception
from nova.network import constants
from nova import objects
from nova import test
from nova.tests import fixtures as nova_fixtures
from nova.tests.functional.api import client as api_client
from nova.tests.functional import fixtures as func_fixtures
from nova.tests.functional import integrated_helpers
from nova.tests.functional import test_servers_resource_request as test_res_req
from nova import utils as nova_utils

CONF = config.CONF
INCOMPLETE_CONSUMER_ID = '00000000-0000-0000-0000-000000000000'


class NovaManageDBIronicTest(test.TestCase):
    def setUp(self):
        super(NovaManageDBIronicTest, self).setUp()
        self.commands = manage.DbCommands()
        self.context = context.RequestContext('fake-user', 'fake-project')

        self.service1 = objects.Service(context=self.context,
                                       host='fake-host1',
                                       binary='nova-compute',
                                       topic='fake-host1',
                                       report_count=1,
                                       disabled=False,
                                       disabled_reason=None,
                                       availability_zone='nova',
                                       forced_down=False)
        self.service1.create()

        self.service2 = objects.Service(context=self.context,
                                       host='fake-host2',
                                       binary='nova-compute',
                                       topic='fake-host2',
                                       report_count=1,
                                       disabled=False,
                                       disabled_reason=None,
                                       availability_zone='nova',
                                       forced_down=False)
        self.service2.create()

        self.service3 = objects.Service(context=self.context,
                                       host='fake-host3',
                                       binary='nova-compute',
                                       topic='fake-host3',
                                       report_count=1,
                                       disabled=False,
                                       disabled_reason=None,
                                       availability_zone='nova',
                                       forced_down=False)
        self.service3.create()

        self.cn1 = objects.ComputeNode(context=self.context,
                                       service_id=self.service1.id,
                                       host='fake-host1',
                                       hypervisor_type='ironic',
                                       vcpus=1,
                                       memory_mb=1024,
                                       local_gb=10,
                                       vcpus_used=1,
                                       memory_mb_used=1024,
                                       local_gb_used=10,
                                       hypervisor_version=0,
                                       hypervisor_hostname='fake-node1',
                                       cpu_info='{}')
        self.cn1.create()

        self.cn2 = objects.ComputeNode(context=self.context,
                                       service_id=self.service1.id,
                                       host='fake-host1',
                                       hypervisor_type='ironic',
                                       vcpus=1,
                                       memory_mb=1024,
                                       local_gb=10,
                                       vcpus_used=1,
                                       memory_mb_used=1024,
                                       local_gb_used=10,
                                       hypervisor_version=0,
                                       hypervisor_hostname='fake-node2',
                                       cpu_info='{}')
        self.cn2.create()

        self.cn3 = objects.ComputeNode(context=self.context,
                                       service_id=self.service2.id,
                                       host='fake-host2',
                                       hypervisor_type='ironic',
                                       vcpus=1,
                                       memory_mb=1024,
                                       local_gb=10,
                                       vcpus_used=1,
                                       memory_mb_used=1024,
                                       local_gb_used=10,
                                       hypervisor_version=0,
                                       hypervisor_hostname='fake-node3',
                                       cpu_info='{}')
        self.cn3.create()

        self.cn4 = objects.ComputeNode(context=self.context,
                                       service_id=self.service3.id,
                                       host='fake-host3',
                                       hypervisor_type='libvirt',
                                       vcpus=1,
                                       memory_mb=1024,
                                       local_gb=10,
                                       vcpus_used=1,
                                       memory_mb_used=1024,
                                       local_gb_used=10,
                                       hypervisor_version=0,
                                       hypervisor_hostname='fake-node4',
                                       cpu_info='{}')
        self.cn4.create()

        self.cn5 = objects.ComputeNode(context=self.context,
                                       service_id=self.service2.id,
                                       host='fake-host2',
                                       hypervisor_type='ironic',
                                       vcpus=1,
                                       memory_mb=1024,
                                       local_gb=10,
                                       vcpus_used=1,
                                       memory_mb_used=1024,
                                       local_gb_used=10,
                                       hypervisor_version=0,
                                       hypervisor_hostname='fake-node5',
                                       cpu_info='{}')
        self.cn5.create()

        self.insts = []
        for cn in (self.cn1, self.cn2, self.cn3, self.cn4, self.cn4, self.cn5):
            flavor = objects.Flavor(extra_specs={})
            inst = objects.Instance(context=self.context,
                                    user_id=self.context.user_id,
                                    project_id=self.context.project_id,
                                    flavor=flavor,
                                    node=cn.hypervisor_hostname,
                                    host=cn.host,
                                    compute_id=cn.id)
            inst.create()
            self.insts.append(inst)

        self.ironic_insts = [i for i in self.insts
                             if i.node != self.cn4.hypervisor_hostname]
        self.virt_insts = [i for i in self.insts
                           if i.node == self.cn4.hypervisor_hostname]


class TestIronicComputeNodeMove(NovaManageDBIronicTest):
    """Functional tests for "nova-manage db ironic_compute_node_move" CLI."""
    api_major_version = 'v2.1'

    def setUp(self):
        super(TestIronicComputeNodeMove, self).setUp()
        self.enforce_fk_constraints()
        self.cli = manage.DbCommands()
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

    def test_ironic_compute_node_move_success(self):
        self.service1.forced_down = True
        self.service1.save()
        self.assertEqual(self.service1.id, self.cn1.service_id)
        # move cn1 on service1 to service2
        node_uuid = self.cn1.uuid
        dest_host = self.service2.host

        self.commands.ironic_compute_node_move(node_uuid, dest_host)

        # check the compute node got moved to service 2
        updated_cn1 = objects.ComputeNode.get_by_id(self.context, self.cn1.id)
        self.assertEqual(self.service2.id, updated_cn1.service_id)
        self.assertEqual(self.service2.host, updated_cn1.host)
        # check the instance got moved too
        updated_instance = objects.Instance.get_by_id(
            self.context, self.insts[0].id)
        self.assertEqual(self.service2.host, updated_instance.host)

    def test_ironic_compute_node_move_raise_not_forced_down(self):
        node_uuid = self.cn1.uuid
        dest_host = self.service2.host

        self.assertRaises(exception.NovaException,
                          self.commands.ironic_compute_node_move,
                          node_uuid, dest_host)

    def test_ironic_compute_node_move_raise_forced_down(self):
        self.service1.forced_down = True
        self.service1.save()
        self.service2.forced_down = True
        self.service2.save()
        node_uuid = self.cn1.uuid
        dest_host = self.service2.host

        self.assertRaises(exception.NovaException,
                          self.commands.ironic_compute_node_move,
                          node_uuid, dest_host)


class NovaManageCellV2Test(test.TestCase):
    def setUp(self):
        super(NovaManageCellV2Test, self).setUp()
        self.commands = manage.CellV2Commands()
        self.context = context.RequestContext('fake-user', 'fake-project')

        self.service1 = objects.Service(context=self.context,
                                        host='fake-host1',
                                        binary='nova-compute',
                                        topic='fake-host1',
                                        report_count=1,
                                        disabled=False,
                                        disabled_reason=None,
                                        availability_zone='nova',
                                        forced_down=False)
        self.service1.create()

        self.cn1 = objects.ComputeNode(context=self.context,
                                       service_id=self.service1.id,
                                       host='fake-host1',
                                       hypervisor_type='ironic',
                                       vcpus=1,
                                       memory_mb=1024,
                                       local_gb=10,
                                       vcpus_used=1,
                                       memory_mb_used=1024,
                                       local_gb_used=10,
                                       hypervisor_version=0,
                                       hypervisor_hostname='fake-node1',
                                       cpu_info='{}')
        self.cn1.create()

    def test_delete_host(self):
        cells = objects.CellMappingList.get_all(self.context)

        self.commands.discover_hosts()

        # We should have one mapped node
        cns = objects.ComputeNodeList.get_all(self.context)
        self.assertEqual(1, len(cns))
        self.assertEqual(1, cns[0].mapped)

        for cell in cells:
            r = self.commands.delete_host(cell.uuid, 'fake-host1')
            if r == 0:
                break

        # Our node should now be unmapped
        cns = objects.ComputeNodeList.get_all(self.context)
        self.assertEqual(1, len(cns))
        self.assertEqual(0, cns[0].mapped)

    def test_delete_cell_force_unmaps_computes(self):
        cells = objects.CellMappingList.get_all(self.context)

        self.commands.discover_hosts()

        # We should have one host mapping
        hms = objects.HostMappingList.get_all(self.context)
        self.assertEqual(1, len(hms))

        # We should have one mapped node
        cns = objects.ComputeNodeList.get_all(self.context)
        self.assertEqual(1, len(cns))
        self.assertEqual(1, cns[0].mapped)

        for cell in cells:
            res = self.commands.delete_cell(cell.uuid, force=True)
            self.assertEqual(0, res)

        # The host mapping should be deleted since the force option is used
        hms = objects.HostMappingList.get_all(self.context)
        self.assertEqual(0, len(hms))

        # All our cells should be deleted
        cells = objects.CellMappingList.get_all(self.context)
        self.assertEqual(0, len(cells))

        # Our node should now be unmapped
        cns = objects.ComputeNodeList.get_all(self.context)
        self.assertEqual(1, len(cns))
        self.assertEqual(0, cns[0].mapped)


class TestNovaManageVolumeAttachmentRefresh(
    integrated_helpers._IntegratedTestBase
):
    """Functional tests for 'nova-manage volume_attachment refresh'."""

    # Required for any multiattach volume tests
    microversion = '2.60'

    def setUp(self):
        super().setUp()
        self.tmpdir = self.useFixture(fixtures.TempDir()).path
        self.ctxt = context.get_admin_context()
        self.cli = manage.VolumeAttachmentCommands()
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))
        self.flags(my_ip='192.168.1.100')
        self.fake_connector = {
            'ip': '192.168.1.128',
            'initiator': 'fake_iscsi.iqn',
            'host': 'compute',
        }
        self.connector_path = os.path.join(self.tmpdir, 'fake_connector')
        with open(self.connector_path, 'w') as fh:
            jsonutils.dump(self.fake_connector, fh)

    def _assert_instance_actions(self, server):
        actions = self.api.get_instance_actions(server['id'])
        self.assertEqual('unlock', actions[0]['action'])
        self.assertEqual('refresh_volume_attachment', actions[1]['action'])
        self.assertEqual('lock', actions[2]['action'])
        self.assertEqual('stop', actions[3]['action'])
        self.assertEqual('attach_volume', actions[4]['action'])
        self.assertEqual('create', actions[5]['action'])

    def test_refresh(self):
        server = self._create_server(networks='none')
        volume_id = self.cinder.IMAGE_BACKED_VOL
        self.api.post_server_volume(
            server['id'], {'volumeAttachment': {'volumeId': volume_id}})
        self._wait_for_volume_attach(server['id'], volume_id)
        self._stop_server(server)

        attachments = self.cinder.volume_to_attachment[volume_id]
        original_attachment_id = list(attachments.keys())[0]

        bdm = objects.BlockDeviceMapping.get_by_volume_and_instance(
            self.ctxt, volume_id, server['id'])
        original_device_name = bdm.device_name
        self.assertEqual(original_attachment_id, bdm.attachment_id)

        # The CinderFixture also stashes the attachment id in the
        # connection_info of the attachment so we can assert when and if it is
        # refreshed by recreating the attachments.
        connection_info = jsonutils.loads(bdm.connection_info)
        self.assertIn('attachment_id', connection_info['data'])
        self.assertEqual(
            original_attachment_id, connection_info['data']['attachment_id'])

        result = self.cli.refresh(
            volume_id=volume_id,
            instance_uuid=server['id'],
            connector_path=self.connector_path)
        self.assertEqual(0, result)

        bdm = objects.BlockDeviceMapping.get_by_volume_and_instance(
            self.ctxt, volume_id, server['id'])

        attachments = self.cinder.volume_to_attachment[volume_id]
        new_attachment_id = list(attachments.keys())[0]

        # Assert that the two attachment ids we have are not the same
        self.assertNotEqual(original_attachment_id, new_attachment_id)

        # Assert that we are using the new attachment id
        self.assertEqual(new_attachment_id, bdm.attachment_id)

        # Assert that this new attachment id is also in the saved
        # connection_info of the bdm that has been refreshed
        connection_info = jsonutils.loads(bdm.connection_info)
        self.assertIn('attachment_id', connection_info['data'])
        self.assertEqual(
            new_attachment_id, connection_info['data']['attachment_id'])

        # Assert that the original device_name is stashed in the connector of
        # the attachment within the fixture.
        attachment_ref = attachments[new_attachment_id]
        connector = attachment_ref.get('connector')
        self.assertEqual(original_device_name, connector.get('device'))

        # Assert that we have actions we expect against the instance
        self._assert_instance_actions(server)

    def test_refresh_rpcapi_remove_volume_connection_rollback(self):
        server = self._create_server(networks='none')
        volume_id = self.cinder.IMAGE_BACKED_VOL
        self.api.post_server_volume(
            server['id'], {'volumeAttachment': {'volumeId': volume_id}})
        self._wait_for_volume_attach(server['id'], volume_id)
        self._stop_server(server)

        attachments = self.cinder.volume_to_attachment[volume_id]
        original_attachment_id = list(attachments.keys())[0]

        bdm = objects.BlockDeviceMapping.get_by_volume_and_instance(
            self.ctxt, volume_id, server['id'])
        self.assertEqual(original_attachment_id, bdm.attachment_id)

        connection_info = jsonutils.loads(bdm.connection_info)
        self.assertIn('attachment_id', connection_info['data'])
        self.assertEqual(
            original_attachment_id, connection_info['data']['attachment_id'])

        with (
            mock.patch(
                'nova.compute.rpcapi.ComputeAPI.remove_volume_connection',
                side_effect=test.TestingException)
        ) as (
            mock_remove_volume_connection
        ):
            result = self.cli.refresh(
                volume_id=volume_id,
                instance_uuid=server['id'],
                connector_path=self.connector_path)

        # Assert that we hit our mock
        mock_remove_volume_connection.assert_called_once()

        # Assert that this is caught as an unknown exception
        self.assertEqual(1, result)

        # Assert that we still only have a single attachment
        attachments = self.cinder.volume_to_attachment[volume_id]
        self.assertEqual(1, len(attachments))
        self.assertEqual(list(attachments.keys())[0], original_attachment_id)

        # Assert that we have actions we expect against the instance
        self._assert_instance_actions(server)

    def test_refresh_cinder_attachment_update_rollback(self):
        server = self._create_server(networks='none')
        volume_id = self.cinder.IMAGE_BACKED_VOL
        self.api.post_server_volume(
            server['id'], {'volumeAttachment': {'volumeId': volume_id}})
        self._wait_for_volume_attach(server['id'], volume_id)
        self._stop_server(server)

        attachments = self.cinder.volume_to_attachment[volume_id]
        original_attachment_id = list(attachments.keys())[0]

        bdm = objects.BlockDeviceMapping.get_by_volume_and_instance(
            self.ctxt, volume_id, server['id'])
        self.assertEqual(original_attachment_id, bdm.attachment_id)

        connection_info = jsonutils.loads(bdm.connection_info)
        self.assertIn('attachment_id', connection_info['data'])
        self.assertEqual(
            original_attachment_id, connection_info['data']['attachment_id'])

        with (
            mock.patch(
                'nova.volume.cinder.API.attachment_update',
                side_effect=test.TestingException, autospec=False)
        ) as (
            mock_attachment_update
        ):
            result = self.cli.refresh(
                volume_id=volume_id,
                instance_uuid=server['id'],
                connector_path=self.connector_path)

        # Assert that we hit our mock
        mock_attachment_update.assert_called_once()

        # Assert that this is caught as an unknown exception
        self.assertEqual(1, result)

        # Assert that we still only have a single attachment
        attachments = self.cinder.volume_to_attachment[volume_id]
        new_attachment_id = list(attachments.keys())[0]
        self.assertEqual(1, len(attachments))
        self.assertNotEqual(new_attachment_id, original_attachment_id)

        # Assert that this new attachment id is saved in the bdm and the stale
        # connection_info associated with the original volume attachment has
        # been cleared.
        bdm = objects.BlockDeviceMapping.get_by_volume_and_instance(
            self.ctxt, volume_id, server['id'])
        self.assertEqual(new_attachment_id, bdm.attachment_id)
        self.assertIsNone(bdm.connection_info)

        # Assert that we have actions we expect against the instance
        self._assert_instance_actions(server)

    def test_refresh_pre_cinderv3_without_attachment_id(self):
        """Test the refresh command when the bdm has no attachment_id.
        """
        server = self._create_server(networks='none')
        volume_id = self.cinder.IMAGE_BACKED_VOL
        self.api.post_server_volume(
            server['id'], {'volumeAttachment': {'volumeId': volume_id}})
        self._wait_for_volume_attach(server['id'], volume_id)
        self._stop_server(server)

        bdm = objects.BlockDeviceMapping.get_by_volume_and_instance(
            self.ctxt, volume_id, server['id'])

        # Drop the attachment_id from the bdm before continuing and delete the
        # attachment from the fixture to mimic this being attached via the
        # legacy export style cinderv2 APIs.
        del self.cinder.volume_to_attachment[volume_id]
        bdm.attachment_id = None
        bdm.save()

        result = self.cli.refresh(
            volume_id=volume_id,
            instance_uuid=server['id'],
            connector_path=self.connector_path)
        self.assertEqual(0, result)

        bdm = objects.BlockDeviceMapping.get_by_volume_and_instance(
            self.ctxt, volume_id, server['id'])

        attachments = self.cinder.volume_to_attachment[volume_id]
        new_attachment_id = list(attachments.keys())[0]

        # Assert that we are using the new attachment id
        self.assertEqual(new_attachment_id, bdm.attachment_id)

        # Assert that this new attachment id is also in the saved
        # connection_info of the bdm that has been refreshed
        connection_info = jsonutils.loads(bdm.connection_info)
        self.assertIn('attachment_id', connection_info['data'])
        self.assertEqual(
            new_attachment_id, connection_info['data']['attachment_id'])

        # Assert that we have actions we expect against the instance
        self._assert_instance_actions(server)

    def test_show_multiattach_volume(self):
        """Test that the show command doesn't fail for multiattach volumes
        """
        volume_id = self.cinder.MULTIATTACH_VOL

        # Launch two instances and attach the same multiattach volume to both
        server_1 = self._create_server(networks='none')
        self.api.post_server_volume(
            server_1['id'], {'volumeAttachment': {'volumeId': volume_id}})
        self._wait_for_volume_attach(server_1['id'], volume_id)

        server_2 = self._create_server(networks='none')
        self.api.post_server_volume(
            server_2['id'], {'volumeAttachment': {'volumeId': volume_id}})
        self._wait_for_volume_attach(server_2['id'], volume_id)

        result = self.cli.show(
            volume_id=volume_id, instance_uuid=server_1['id'])

        # Assert that the command completes successfully, this was previously
        # broken and documented under bug #1945452
        self.assertEqual(0, result)


class TestNovaManagePlacementHealAllocations(
        integrated_helpers.ProviderUsageBaseTestCase):
    """Functional tests for nova-manage placement heal_allocations"""

    # This is required by the parent class.
    compute_driver = 'fake.SmallFakeDriver'
    # We want to test iterating across multiple cells.
    NUMBER_OF_CELLS = 2

    def setUp(self):
        super(TestNovaManagePlacementHealAllocations, self).setUp()
        self.useFixture(nova_fixtures.CinderFixture(self))
        self.cli = manage.PlacementCommands()
        # We need to start a compute in each non-cell0 cell.
        for cell_name, cell_mapping in self.cell_mappings.items():
            if cell_mapping.uuid == objects.CellMapping.CELL0_UUID:
                continue
            self._start_compute(cell_name, cell_name=cell_name)
        # Make sure we have two hypervisors reported in the API.
        hypervisors = self.admin_api.api_get(
            '/os-hypervisors').body['hypervisors']
        self.assertEqual(2, len(hypervisors))
        self.flavor = self.api.get_flavors()[0]
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

    def _boot_and_remove_allocations(
        self, flavor, hostname, volume_backed=False,
    ):
        """Creates a server on the given host and remove all allocations.

        :param flavor: the flavor used to create the server
        :param hostname: the host on which to create the server
        :param volume_backed: True if the server should be volume-backed and
            as a result not have any DISK_GB allocation
        :returns: two-item tuple of the server and the compute node resource
            provider UUID
        """
        server_req = self._build_server(
            image_uuid='155d900f-4e14-4e4c-a73d-069cbf4541e6',
            flavor_id=flavor['id'],
            networks='none',
            az=f'nova:{hostname}')
        if volume_backed:
            vol_id = nova_fixtures.CinderFixture.IMAGE_BACKED_VOL
            server_req['block_device_mapping_v2'] = [{
                'source_type': 'volume',
                'destination_type': 'volume',
                'boot_index': 0,
                'uuid': vol_id
            }]
            server_req['imageRef'] = ''
        created_server = self.api.post_server({'server': server_req})
        server = self._wait_for_state_change(created_server, 'ACTIVE')

        # Verify that our source host is what the server ended up on
        self.assertEqual(hostname, server['OS-EXT-SRV-ATTR:host'])

        # Delete the server's allocations
        self._delete_server_allocations(server['id'])

        # Check that the compute node resource provider has no allocations.
        rp_uuid = self._get_provider_uuid_by_host(hostname)
        provider_usages = self._get_provider_usages(rp_uuid)
        for resource_class, usage in provider_usages.items():
            self.assertEqual(
                0, usage,
                'Compute node resource provider %s should not have %s '
                'usage; something must be wrong in test setup.' %
                (hostname, resource_class))

        # Check that the server has no allocations.
        allocations = self._get_allocations_by_server_uuid(server['id'])
        self.assertEqual({}, allocations,
                         'Server should not have allocations; something must '
                         'be wrong in test setup.')
        return server, rp_uuid

    def _assert_healed(self, server, rp_uuid):
        allocations = self._get_allocations_by_server_uuid(server['id'])
        self.assertIn(rp_uuid, allocations,
                      'Allocations not found for server %s and compute node '
                      'resource provider. %s\nOutput:%s' %
                      (server['id'], rp_uuid, self.output.getvalue()))
        self.assertFlavorMatchesAllocation(self.flavor, server['id'], rp_uuid)

    def test_heal_allocations_paging(self):
        """This test runs the following scenario:

        * Schedule server1 to cell1 and assert it doesn't have allocations.
        * Schedule server2 to cell2 and assert it doesn't have allocations.
        * Run "nova-manage placement heal_allocations --max-count 1" to make
          sure we stop with just one instance and the return code is 1.
        * Run "nova-manage placement heal_allocations" and assert both
          both instances now have allocations against their respective compute
          node resource providers.
        """
        server1, rp_uuid1 = self._boot_and_remove_allocations(
            self.flavor, 'cell1')
        server2, rp_uuid2 = self._boot_and_remove_allocations(
            self.flavor, 'cell2')

        # heal server1 and server2 in separate calls
        for x in range(2):
            result = self.cli.heal_allocations(max_count=1, verbose=True)
            self.assertEqual(1, result, self.output.getvalue())
            output = self.output.getvalue()
            self.assertIn('Max count reached. Processed 1 instances.', output)
            # If this is the 2nd call, we'll have skipped the first instance.
            if x == 0:
                self.assertNotIn('is up-to-date', output)
            else:
                self.assertIn('is up-to-date', output)

        self._assert_healed(server1, rp_uuid1)
        self._assert_healed(server2, rp_uuid2)

        # run it again to make sure nothing was processed
        result = self.cli.heal_allocations(verbose=True)
        self.assertEqual(4, result, self.output.getvalue())
        self.assertIn('is up-to-date', self.output.getvalue())

    def test_heal_allocations_paging_max_count_more_than_num_instances(self):
        """Sets up 2 instances in cell1 and 1 instance in cell2. Then specify
        --max-count=10, processes 3 instances, rc is 0
        """
        servers = []  # This is really a list of 2-item tuples.
        for x in range(2):
            servers.append(
                self._boot_and_remove_allocations(self.flavor, 'cell1'))
        servers.append(
            self._boot_and_remove_allocations(self.flavor, 'cell2'))
        result = self.cli.heal_allocations(max_count=10, verbose=True)
        self.assertEqual(0, result, self.output.getvalue())
        self.assertIn('Processed 3 instances.', self.output.getvalue())
        for server, rp_uuid in servers:
            self._assert_healed(server, rp_uuid)

    def test_heal_allocations_paging_more_instances_remain(self):
        """Tests that there is one instance in cell1 and two instances in
        cell2, with a --max-count=2. This tests that we stop in cell2 once
        max_count is reached.
        """
        servers = []  # This is really a list of 2-item tuples.
        servers.append(
            self._boot_and_remove_allocations(self.flavor, 'cell1'))
        for x in range(2):
            servers.append(
                self._boot_and_remove_allocations(self.flavor, 'cell2'))
        result = self.cli.heal_allocations(max_count=2, verbose=True)
        self.assertEqual(1, result, self.output.getvalue())
        self.assertIn('Max count reached. Processed 2 instances.',
                      self.output.getvalue())
        # Assert that allocations were healed on the instances we expect. Order
        # works here because cell mappings are retrieved by id in ascending
        # order so oldest to newest, and instances are also retrieved from each
        # cell by created_at in ascending order, which matches the order we put
        # created servers in our list.
        for x in range(2):
            self._assert_healed(*servers[x])
        # And assert the remaining instance does not have allocations.
        allocations = self._get_allocations_by_server_uuid(
            servers[2][0]['id'])
        self.assertEqual({}, allocations)

    def test_heal_allocations_unlimited(self):
        """Sets up 2 instances in cell1 and 1 instance in cell2. Then
        don't specify --max-count, processes 3 instances, rc is 0.
        """
        servers = []  # This is really a list of 2-item tuples.
        for x in range(2):
            servers.append(
                self._boot_and_remove_allocations(self.flavor, 'cell1'))
        servers.append(
            self._boot_and_remove_allocations(self.flavor, 'cell2'))
        result = self.cli.heal_allocations(verbose=True)
        self.assertEqual(0, result, self.output.getvalue())
        self.assertIn('Processed 3 instances.', self.output.getvalue())
        for server, rp_uuid in servers:
            self._assert_healed(server, rp_uuid)

    def test_heal_allocations_shelved(self):
        """Tests the scenario that an instance with no allocations is shelved
        so heal_allocations skips it (since the instance is not on a host).
        """
        server, rp_uuid = self._boot_and_remove_allocations(
            self.flavor, 'cell1')
        self.api.post_server_action(server['id'], {'shelve': None})
        # The server status goes to SHELVED_OFFLOADED before the host/node
        # is nulled out in the compute service, so we also have to wait for
        # that so we don't race when we run heal_allocations.
        server = self._wait_for_server_parameter(server,
            {'OS-EXT-SRV-ATTR:host': None, 'status': 'SHELVED_OFFLOADED'})
        result = self.cli.heal_allocations(verbose=True)
        self.assertEqual(4, result, self.output.getvalue())
        self.assertIn('Instance %s is not on a host.' % server['id'],
                      self.output.getvalue())
        # Check that the server has no allocations.
        allocations = self._get_allocations_by_server_uuid(server['id'])
        self.assertEqual({}, allocations,
                         'Shelved-offloaded server should not have '
                         'allocations.')

    def test_heal_allocations_task_in_progress(self):
        """Tests the case that heal_allocations skips over an instance which
        is undergoing a task state transition (in this case pausing).
        """
        server, rp_uuid = self._boot_and_remove_allocations(
            self.flavor, 'cell1')

        def fake_pause_instance(_self, ctxt, instance, *a, **kw):
            self.assertEqual('pausing', instance.task_state)
        # We have to stub out pause_instance so that the instance is stuck with
        # task_state != None.
        self.stub_out('nova.compute.manager.ComputeManager.pause_instance',
                      fake_pause_instance)
        self.api.post_server_action(server['id'], {'pause': None})
        result = self.cli.heal_allocations(verbose=True)
        self.assertEqual(4, result, self.output.getvalue())
        # Check that the server has no allocations.
        allocations = self._get_allocations_by_server_uuid(server['id'])
        self.assertEqual({}, allocations,
                         'Server undergoing task state transition should '
                         'not have allocations.')
        # Assert something was logged for this instance when it was skipped.
        self.assertIn('Instance %s is undergoing a task state transition: '
                      'pausing' % server['id'], self.output.getvalue())

    def test_heal_allocations_ignore_deleted_server(self):
        """Creates two servers, deletes one, and then runs heal_allocations
        to make sure deleted servers are filtered out.
        """
        # Create a server that we'll leave alive
        self._boot_and_remove_allocations(self.flavor, 'cell1')
        # and another that we'll delete
        server, _ = self._boot_and_remove_allocations(self.flavor, 'cell1')
        self._delete_server(server)
        result = self.cli.heal_allocations(verbose=True)
        self.assertEqual(0, result, self.output.getvalue())
        self.assertIn('Processed 1 instances.', self.output.getvalue())

    def test_heal_allocations_update_sentinel_consumer(self):
        """Tests the scenario that allocations were created before microversion
        1.8 when consumer (project_id and user_id) were not required so the
        consumer information is using sentinel values from config.

        Since the hacked scheduler used in this test class won't actually
        create allocations during scheduling, we have to create the allocations
        out-of-band and then run our heal routine to see they get updated with
        the instance project and user information.
        """
        server, rp_uuid = self._boot_and_remove_allocations(
            self.flavor, 'cell1')
        # Now we'll create allocations using microversion < 1.8 to so that
        # placement creates the consumer record with the config-based project
        # and user values.
        alloc_body = {
            "allocations": [
                {
                    "resource_provider": {
                        "uuid": rp_uuid
                    },
                    "resources": {
                        "MEMORY_MB": self.flavor['ram'],
                        "VCPU": self.flavor['vcpus'],
                        "DISK_GB": self.flavor['disk']
                    }
                }
            ]
        }
        self.placement.put('/allocations/%s' % server['id'], alloc_body)
        # Make sure we did that correctly. Use version 1.12 so we can assert
        # the project_id and user_id are based on the sentinel values.
        allocations = self.placement.get(
            '/allocations/%s' % server['id'], version='1.12').body
        self.assertEqual(INCOMPLETE_CONSUMER_ID, allocations['project_id'])
        self.assertEqual(INCOMPLETE_CONSUMER_ID, allocations['user_id'])
        allocations = allocations['allocations']
        self.assertIn(rp_uuid, allocations)
        self.assertFlavorMatchesAllocation(self.flavor, server['id'], rp_uuid)
        # First do a dry run.
        result = self.cli.heal_allocations(verbose=True, dry_run=True)
        # Nothing changed so the return code should be 4.
        self.assertEqual(4, result, self.output.getvalue())
        output = self.output.getvalue()
        self.assertIn('Processed 0 instances.', output)
        self.assertIn('[dry-run] Update allocations for instance %s'
                      % server['id'], output)
        # Now run heal_allocations which should update the consumer info.
        result = self.cli.heal_allocations(verbose=True)
        self.assertEqual(0, result, self.output.getvalue())
        output = self.output.getvalue()
        self.assertIn(
            'Successfully updated allocations for', output)
        self.assertIn('Processed 1 instances.', output)
        # Now assert that the consumer was actually updated.
        allocations = self.placement.get(
            '/allocations/%s' % server['id'], version='1.12').body
        self.assertEqual(server['tenant_id'], allocations['project_id'])
        self.assertEqual(server['user_id'], allocations['user_id'])

    def test_heal_allocations_dry_run(self):
        """Tests to make sure the --dry-run option does not commit changes."""
        # Create a server with no allocations.
        server, rp_uuid = self._boot_and_remove_allocations(
            self.flavor, 'cell1')
        result = self.cli.heal_allocations(verbose=True, dry_run=True)
        # Nothing changed so the return code should be 4.
        self.assertEqual(4, result, self.output.getvalue())
        output = self.output.getvalue()
        self.assertIn('Processed 0 instances.', output)
        self.assertIn('[dry-run] Create allocations for instance '
                      '%s' % server['id'], output)
        self.assertIn(rp_uuid, output)

    def test_heal_allocations_specific_instance(self):
        """Tests the case that a specific instance is processed and only that
        instance even though there are two which require processing.
        """
        # Create one that we won't process.
        self._boot_and_remove_allocations(
            self.flavor, 'cell1')
        # Create another that we will process specifically.
        server, rp_uuid = self._boot_and_remove_allocations(
            self.flavor, 'cell1', volume_backed=True)
        # First do a dry run to make sure two instances need processing.
        result = self.cli.heal_allocations(
            max_count=2, verbose=True, dry_run=True)
        # Nothing changed so the return code should be 4.
        self.assertEqual(4, result, self.output.getvalue())
        output = self.output.getvalue()
        self.assertIn('Found 2 candidate instances', output)

        # Now run with our specific instance and it should be the only one
        # processed. Also run with max_count specified to show it's ignored.
        result = self.cli.heal_allocations(
            max_count=10, verbose=True, instance_uuid=server['id'])
        output = self.output.getvalue()
        self.assertEqual(0, result, self.output.getvalue())
        self.assertIn('Found 1 candidate instances', output)
        self.assertIn('Processed 1 instances.', output)
        # There shouldn't be any messages about running in batches.
        self.assertNotIn('Running batches', output)
        # There shouldn't be any message about max count reached.
        self.assertNotIn('Max count reached.', output)
        # Make sure there is no DISK_GB allocation for the volume-backed
        # instance but there is a VCPU allocation based on the flavor.
        allocs = self._get_allocations_by_server_uuid(
            server['id'])[rp_uuid]['resources']
        self.assertNotIn('DISK_GB', allocs)
        self.assertEqual(self.flavor['vcpus'], allocs['VCPU'])

        # Now run it again on the specific instance and it should be done.
        result = self.cli.heal_allocations(
            verbose=True, instance_uuid=server['id'])
        output = self.output.getvalue()
        self.assertEqual(4, result, self.output.getvalue())
        self.assertIn('Found 1 candidate instances', output)
        self.assertIn('Processed 0 instances.', output)
        # There shouldn't be any message about max count reached.
        self.assertNotIn('Max count reached.', output)

        # Delete the instance mapping and make sure that results in an error
        # when we run the command.
        ctxt = context.get_admin_context()
        im = objects.InstanceMapping.get_by_instance_uuid(ctxt, server['id'])
        im.destroy()
        result = self.cli.heal_allocations(
            verbose=True, instance_uuid=server['id'])
        output = self.output.getvalue()
        self.assertEqual(127, result, self.output.getvalue())
        self.assertIn('Unable to find cell for instance %s, is it mapped?' %
                      server['id'], output)

    def test_heal_allocations_specific_cell(self):
        """Tests the case that a specific cell is processed and only that
        cell even though there are two which require processing.
        """
        # Create one that we won't process.
        server1, rp_uuid1 = self._boot_and_remove_allocations(
            self.flavor, 'cell1')
        # Create another that we will process specifically.
        server2, rp_uuid2 = self._boot_and_remove_allocations(
            self.flavor, 'cell2')

        # Get Cell_id of cell2
        cell2_id = self.cell_mappings['cell2'].uuid

        # First do a dry run to make sure two instances need processing.
        result = self.cli.heal_allocations(
            max_count=2, verbose=True, dry_run=True)
        # Nothing changed so the return code should be 4.
        self.assertEqual(4, result, self.output.getvalue())
        output = self.output.getvalue()
        self.assertIn('Found 1 candidate instances', output)

        # Now run with our specific cell and it should be the only one
        # processed.
        result = self.cli.heal_allocations(verbose=True,
                                           cell_uuid=cell2_id)
        output = self.output.getvalue()
        self.assertEqual(0, result, self.output.getvalue())
        self.assertIn('Found 1 candidate instances', output)
        self.assertIn('Processed 1 instances.', output)

        # Now run it again on the specific cell and it should be done.
        result = self.cli.heal_allocations(
            verbose=True, cell_uuid=cell2_id)
        output = self.output.getvalue()
        self.assertEqual(4, result, self.output.getvalue())
        self.assertIn('Found 1 candidate instances', output)
        self.assertIn('Processed 0 instances.', output)

    def test_heal_allocations_force_allocation(self):
        """Tests the case that a specific instance allocations are
        forcefully changed.
        1. create server without allocations
        2. heal allocations without forcing them.
           Assert the allocations match the flavor
        3. update the allocations to change MEMORY_MB to not match the flavor
        4. run heal allocations without --force.
           Assert the allocations still have the bogus
           MEMORY_MB value since they were not forcefully updated.
        5. run heal allocations with --force.
           Assert the allocations match the flavor again
        6. run heal allocations again.
           You should get rc=4 back since nothing changed.
        """
        # 1. Create server that we will forcefully heal specifically.
        server, rp_uuid = self._boot_and_remove_allocations(
            self.flavor, 'cell1', volume_backed=True)

        # 2. heal allocations without forcing them
        result = self.cli.heal_allocations(
            verbose=True, instance_uuid=server['id']
        )
        self.assertEqual(0, result, self.output.getvalue())

        # assert the allocations match the flavor
        allocs = self._get_allocations_by_server_uuid(
          server['id'])[rp_uuid]['resources']
        self.assertEqual(self.flavor['vcpus'], allocs['VCPU'])
        self.assertEqual(self.flavor['ram'], allocs['MEMORY_MB'])

        # 3. update the allocations to change MEMORY_MB
        # to not match the flavor
        alloc_body = {
            "allocations": [
                {
                    "resource_provider": {
                        "uuid": rp_uuid
                    },
                    "resources": {
                        "MEMORY_MB": 1024,
                        "VCPU": self.flavor['vcpus'],
                        "DISK_GB": self.flavor['disk']
                    }
                }
            ]
        }
        self.placement.put('/allocations/%s' % server['id'], alloc_body)

        # Check allocation to see if memory has changed
        allocs = self._get_allocations_by_server_uuid(
            server['id'])[rp_uuid]['resources']
        self.assertEqual(self.flavor['vcpus'], allocs['VCPU'])
        self.assertEqual(1024, allocs['MEMORY_MB'])

        # 4. run heal allocations without --force
        result = self.cli.heal_allocations(
            verbose=True, instance_uuid=server['id']
        )
        self.assertEqual(0, result, self.output.getvalue())
        self.assertIn(
            'Successfully updated allocations for',
            self.output.getvalue())

        # assert the allocations still have the bogus memory
        allocs = self._get_allocations_by_server_uuid(
          server['id'])[rp_uuid]['resources']
        self.assertEqual(1024, allocs['MEMORY_MB'])

        # call heal without force flag
        # rc should be 4 since force flag was not used.
        result = self.cli.heal_allocations(
            verbose=True, instance_uuid=server['id']
        )
        self.assertEqual(4, result, self.output.getvalue())

        # call heal with force flag and dry run
        result = self.cli.heal_allocations(
            dry_run=True, verbose=True,
            instance_uuid=server['id'],
            force=True
        )
        self.assertEqual(4, result, self.output.getvalue())
        self.assertIn(
            '[dry-run] Update allocations for instance',
            self.output.getvalue())

        # assert nothing has changed after dry run
        allocs = self._get_allocations_by_server_uuid(
          server['id'])[rp_uuid]['resources']
        self.assertEqual(1024, allocs['MEMORY_MB'])

        # 5. run heal allocations with --force
        result = self.cli.heal_allocations(
            verbose=True, instance_uuid=server['id'],
            force=True
        )
        self.assertEqual(0, result, self.output.getvalue())
        self.assertIn('Force flag passed for instance',
                      self.output.getvalue())
        self.assertIn('Successfully updated allocations',
                      self.output.getvalue())

        # assert the allocations match the flavor again
        allocs = self._get_allocations_by_server_uuid(
            server['id'])[rp_uuid]['resources']
        self.assertEqual(self.flavor['ram'], allocs['MEMORY_MB'])

        # 6. run heal allocations again and you should get rc=4
        # back since nothing changed
        result = self.cli.heal_allocations(
            verbose=True, instance_uuid=server['id']
        )
        self.assertEqual(4, result, self.output.getvalue())

    def test_instance_with_vgpu_is_blocked(self):
        # we cannot boot with VGPU in these tests so manipulate the
        # instance.flavor directly after the boot to simulate an instance with
        # VGPU request
        server, _ = self._boot_and_remove_allocations(self.flavor, 'cell1')
        instance = objects.Instance.get_by_uuid(
            context.get_admin_context(), server['id'])
        instance.flavor.extra_specs["resources:VGPU"] = 1
        instance.save()

        result = self.cli.heal_allocations(
            verbose=True, instance_uuid=server['id'],
            force=True
        )

        self.assertIn(
            f"Healing allocation for instance {server['id']} with vGPU "
            f"resource request is not supported.",
            self.output.getvalue()
        )
        self.assertEqual(8, result, self.output.getvalue())

    def test_instance_with_cyborg_dev_profile_is_blocked(self):
        # we cannot boot with cyborg device in these tests so manipulate the
        # instance.flavor directly after the boot to simulate an instance with
        # cyborg request
        server, _ = self._boot_and_remove_allocations(self.flavor, 'cell1')
        instance = objects.Instance.get_by_uuid(
            context.get_admin_context(), server['id'])
        instance.flavor.extra_specs["accel:device_profile"] = "foo"
        instance.save()

        result = self.cli.heal_allocations(
            verbose=True, instance_uuid=server['id'],
            force=True
        )

        self.assertIn(
            f"Healing allocation for instance {server['id']} with Cyborg "
            f"device profile request is not supported.",
            self.output.getvalue()
        )
        self.assertEqual(8, result, self.output.getvalue())


class TestNovaManagePlacementHealPortAllocations(
    test_res_req.PortResourceRequestBasedSchedulingTestBase
):

    def setUp(self):
        super(TestNovaManagePlacementHealPortAllocations, self).setUp()
        self.cli = manage.PlacementCommands()
        self.flavor = self.api.get_flavors()[0]
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

        # Make it easier to debug failed test cases
        def print_stdout_on_fail(*args, **kwargs):
            import sys
            sys.stderr.write(self.output.getvalue())

        self.addOnException(print_stdout_on_fail)

    def _add_resource_request_to_a_bound_port(self, port_id, resource_request):
        # NOTE(gibi): self.neutron._ports contains a copy of each neutron port
        # defined on class level in the fixture. So modifying what is in the
        # _ports list is safe as it is re-created for each Neutron fixture
        # instance therefore for each individual test using that fixture.
        bound_port = self.neutron._ports[port_id]
        bound_port[constants.RESOURCE_REQUEST] = resource_request

    @staticmethod
    def _get_default_resource_request(port_uuid):
        return {
            "resources": {
                orc.NET_BW_IGR_KILOBIT_PER_SEC: 1000,
                orc.NET_BW_EGR_KILOBIT_PER_SEC: 1000},
            "required": ["CUSTOM_PHYSNET2", "CUSTOM_VNIC_TYPE_NORMAL"]
        }

    def _create_server_with_missing_port_alloc(
            self, ports, resource_request=None):

        server = self._create_server(
            flavor=self.flavor,
            networks=[{'port': port['id']} for port in ports])
        server = self._wait_for_state_change(server, 'ACTIVE')

        # This is a hack to simulate that we have a server that is missing
        # allocation for its port
        for port in ports:
            if not resource_request:
                rr = self._get_default_resource_request(port['id'])
            else:
                rr = resource_request

            self._add_resource_request_to_a_bound_port(port['id'], rr)

        updated_ports = [
            self.neutron.show_port(port['id'])['port'] for port in ports]

        return server, updated_ports

    def _get_resource_request(self, port):
        res_req = port[constants.RESOURCE_REQUEST]
        return res_req

    def _assert_placement_updated(self, server, ports):
        rsp = self.placement.get(
            '/allocations/%s' % server['id'],
            version=1.28).body

        allocations = rsp['allocations']

        # we expect one allocation for the compute resources and one for the
        # networking resources
        self.assertEqual(2, len(allocations))
        self.assertEqual(
            self._resources_from_flavor(self.flavor),
            allocations[self.compute1_rp_uuid]['resources'])

        self.assertEqual(server['tenant_id'], rsp['project_id'])
        self.assertEqual(server['user_id'], rsp['user_id'])

        network_allocations = allocations[
            self.ovs_bridge_rp_per_host[self.compute1_rp_uuid]]['resources']

        # this code assumes that every port is allocated from the same OVS
        # bridge RP
        total_request = collections.defaultdict(int)
        for port in ports:
            port_request = self._get_resource_request(port)['resources']
            for rc, amount in port_request.items():
                total_request[rc] += amount
        self.assertEqual(total_request, network_allocations)

    def _assert_port_updated(self, port_uuid):
        updated_port = self.neutron.show_port(port_uuid)['port']
        binding_profile = updated_port.get('binding:profile', {})
        self.assertEqual(
            self.ovs_bridge_rp_per_host[self.compute1_rp_uuid],
            binding_profile['allocation'])

    def _assert_ports_updated(self, ports):
        for port in ports:
            self._assert_port_updated(port['id'])

    def _assert_placement_not_updated(self, server):
        allocations = self.placement.get(
            '/allocations/%s' % server['id']).body['allocations']
        self.assertEqual(1, len(allocations))
        self.assertIn(self.compute1_rp_uuid, allocations)

    def _assert_port_not_updated(self, port_uuid):
        updated_port = self.neutron.show_port(port_uuid)['port']
        binding_profile = updated_port.get('binding:profile', {})
        self.assertNotIn('allocation', binding_profile)

    def _assert_ports_not_updated(self, ports):
        for port in ports:
            self._assert_port_not_updated(port['id'])

    def test_heal_port_allocation_only(self):
        """Test that only port allocation needs to be healed for an instance.

        * boot with a neutron port that does not have resource request
        * hack in a resource request for the bound port
        * heal the allocation
        * check if the port allocation is created in placement and the port
          is updated in neutron

        """
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        # let's trigger a heal
        result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_updated(server, ports)
        self._assert_ports_updated(ports)

        self.assertIn(
            'Successfully updated allocations',
            self.output.getvalue())
        self.assertEqual(0, result)

    def test_heal_port_allocation_dry_run(self):
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        # let's trigger a heal
        result = self.cli.heal_allocations(
            verbose=True, max_count=2, dry_run=True)

        self._assert_placement_not_updated(server)
        self._assert_ports_not_updated(ports)

        self.assertIn(
            '[dry-run] Update allocations for instance',
            self.output.getvalue())
        # Note that we had a issues by printing defaultdicts directly to the
        # user in the past. So let's assert it does not happen any more.
        self.assertNotIn('defaultdict', self.output.getvalue())
        self.assertEqual(4, result)

    def test_no_healing_is_needed(self):
        """Test that the instance has a port that has allocations
        so nothing to be healed.
        """
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        # heal it once
        result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_updated(server, ports)
        self._assert_ports_updated(ports)

        self.assertIn(
            'Successfully updated allocations',
            self.output.getvalue())
        self.assertEqual(0, result)

        # try to heal it again
        result = self.cli.heal_allocations(verbose=True, max_count=2)

        # nothing is removed
        self._assert_placement_updated(server, ports)
        self._assert_ports_updated(ports)

        # healing was not needed
        self.assertIn(
            'Nothing to be healed.',
            self.output.getvalue())
        self.assertEqual(4, result)

    def test_skip_heal_port_allocation(self):
        """Test that only port allocation needs to be healed for an instance
        but port healing is skipped on the cli.
        """
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        # let's trigger a heal
        result = self.cli.heal_allocations(
            verbose=True, max_count=2, skip_port_allocations=True)

        self._assert_placement_not_updated(server)
        self._assert_ports_not_updated(ports)

        output = self.output.getvalue()
        self.assertNotIn('Updating port', output)
        self.assertIn('Nothing to be healed', output)
        self.assertEqual(4, result)

    def test_skip_heal_port_allocation_but_heal_the_rest(self):
        """Test that the instance doesn't have allocation at all, needs
        allocation for ports as well, but only heal the non port related
        allocation.
        """
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        # delete the server allocation in placement to simulate that it needs
        # to be healed

        # NOTE(gibi): putting empty allocation will delete the consumer in
        # placement
        allocations = self.placement.get(
            '/allocations/%s' % server['id'], version=1.28).body
        allocations['allocations'] = {}
        self.placement.put(
            '/allocations/%s' % server['id'], allocations, version=1.28)

        # let's trigger a heal
        result = self.cli.heal_allocations(
            verbose=True, max_count=2, skip_port_allocations=True)

        # this actually checks that the server has its non port related
        # allocation in placement
        self._assert_placement_not_updated(server)
        self._assert_ports_not_updated(ports)

        output = self.output.getvalue()
        self.assertIn(
            'Successfully created allocations for instance', output)
        self.assertEqual(0, result)

    def test_heal_port_allocation_and_project_id(self):
        """Test that not just port allocation needs to be healed but also the
        missing project_id and user_id.
        """
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        # override allocation with  placement microversion <1.8 to simulate
        # missing project_id and user_id
        alloc_body = {
            "allocations": [
                {
                    "resource_provider": {
                        "uuid": self.compute1_rp_uuid
                    },
                    "resources": {
                        "MEMORY_MB": self.flavor['ram'],
                        "VCPU": self.flavor['vcpus'],
                        "DISK_GB": self.flavor['disk']
                    }
                }
            ]
        }
        self.placement.put('/allocations/%s' % server['id'], alloc_body)

        # let's trigger a heal
        result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_updated(server, ports)
        self._assert_ports_updated(ports)

        output = self.output.getvalue()

        self.assertIn(
            'Successfully updated allocations for instance', output)
        self.assertIn('Processed 1 instances.', output)

        self.assertEqual(0, result)

    def test_heal_allocation_create_allocation_with_port_allocation(self):
        """Test that the instance doesn't have allocation at all but needs
        allocation for the ports as well.
        """
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        # delete the server allocation in placement to simulate that it needs
        # to be healed

        # NOTE(gibi): putting empty allocation will delete the consumer in
        # placement
        allocations = self.placement.get(
            '/allocations/%s' % server['id'], version=1.28).body
        allocations['allocations'] = {}
        self.placement.put(
            '/allocations/%s' % server['id'], allocations, version=1.28)

        # let's trigger a heal
        result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_updated(server, ports)
        self._assert_ports_updated(ports)

        output = self.output.getvalue()
        self.assertIn(
            'Successfully created allocations for instance', output)
        self.assertEqual(0, result)

    @staticmethod
    def _get_too_big_resource_request():
        # The port will request too much NET_BW_IGR_KILOBIT_PER_SEC so there is
        # no RP on the host that can provide it.
        return {
            "resources": {
                orc.NET_BW_IGR_KILOBIT_PER_SEC: 100000000000,
                orc.NET_BW_EGR_KILOBIT_PER_SEC: 1000},
            "required": ["CUSTOM_PHYSNET2",
                         "CUSTOM_VNIC_TYPE_NORMAL"]
        }

    def test_heal_port_allocation_not_enough_resources_for_port(self):
        """Test that a port needs allocation but not enough inventory
        available.
        """
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1], self._get_too_big_resource_request())

        # let's trigger a heal
        result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_not_updated(server)
        self._assert_ports_not_updated(ports)

        output = self.output.getvalue()
        self.assertIn(
            'Placement returned no allocation candidate',
            output)
        self.assertEqual(3, result)

    @staticmethod
    def _get_ambiguous_resource_request():
        return {
            "resources": {
                orc.NET_BW_IGR_KILOBIT_PER_SEC: 1000,
                orc.NET_BW_EGR_KILOBIT_PER_SEC: 1000},
            "required": ["CUSTOM_PHYSNET2",
                         "CUSTOM_VNIC_TYPE_DIRECT"]
        }

    def test_heal_port_allocation_ambiguous_candidates(self):
        """Test that there are more than one matching set of RPs are available
        on the compute.
        """
        # Add bandwidth inventory for PF3 so that both FP2 and FP3 could
        # support the port's request making the situation ambiguous
        inventories = {
            orc.NET_BW_IGR_KILOBIT_PER_SEC: {"total": 100000},
            orc.NET_BW_EGR_KILOBIT_PER_SEC: {"total": 100000},
        }
        self._set_provider_inventories(
            self.sriov_dev_rp_per_host[self.compute1_rp_uuid][self.PF3],
            {"inventories": inventories}
        )

        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1], self._get_ambiguous_resource_request())

        # let's trigger a heal
        result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_not_updated(server)
        self._assert_ports_not_updated(ports)

        self.assertIn(
            ' Placement returned more than one possible allocation candidates',
            self.output.getvalue())
        self.assertEqual(3, result)

    def test_heal_port_allocation_neutron_unavailable_during_port_query(self):
        """Test that Neutron is not available when querying ports.
        """
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        with mock.patch.object(
                self.neutron, "list_ports",
                side_effect=neutron_client_exc.Unauthorized()):
            # let's trigger a heal
            result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_not_updated(server)
        self._assert_ports_not_updated(ports)

        self.assertIn(
            'Unable to query ports for instance',
            self.output.getvalue())
        self.assertEqual(5, result)

    def test_heal_port_allocation_neutron_unavailable(self):
        """Test that the port cannot be updated in Neutron with RP uuid as
        Neutron is unavailable.
        """
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        with mock.patch.object(
                self.neutron, "update_port",
                side_effect=neutron_client_exc.Forbidden()):
            # let's trigger a heal
            result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_not_updated(server)
        self._assert_ports_not_updated(ports)

        self.assertIn(
            'Unable to update ports with allocations',
            self.output.getvalue())
        self.assertEqual(6, result)

    def test_heal_multiple_port_allocations_rollback_success(self):
        """Test neutron port update rollback happy case. Try to heal two ports
        and make the second port update to fail in neutron. Assert that the
        first port update rolled back successfully.
        """
        port2 = self.neutron.create_port()['port']
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1, port2])

        orig_update_port = self.neutron.update_port
        update = []

        def fake_update_port(*args, **kwargs):
            if len(update) == 0 or len(update) > 1:
                update.append(True)
                return orig_update_port(*args, **kwargs)
            if len(update) == 1:
                update.append(True)
                raise neutron_client_exc.Forbidden()

        with mock.patch.object(
                self.neutron, "update_port", side_effect=fake_update_port):
            # let's trigger a heal
            result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_not_updated(server)
        # Actually one of the ports were updated but the update is rolled
        # back when the second neutron port update failed
        self._assert_ports_not_updated(ports)

        output = self.output.getvalue()
        self.assertIn(
            'Rolling back port update',
            output)
        self.assertIn(
            'Unable to update ports with allocations',
            output)
        self.assertEqual(6, result)

    def test_heal_multiple_port_allocations_rollback_fails(self):
        """Test neutron port update rollback error case. Try to heal three
        ports and make the last port update to fail in neutron. Also make the
        rollback of the second port update to fail.
        """
        port2 = self.neutron.create_port()['port']
        port3 = self.neutron.create_port()['port']
        server, _ = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1, port2, port3])

        orig_update_port = self.neutron.update_port
        port_updates = []

        def fake_update_port(port_id, *args, **kwargs):
            # 0, 1: the first two update operation succeeds
            # 4: the last rollback operation succeeds
            if len(port_updates) in [0, 1, 4]:
                port_updates.append(port_id)
                return orig_update_port(port_id, *args, **kwargs)
            # 2 : last update operation fails
            # 3 : the first rollback operation also fails
            if len(port_updates) in [2, 3]:
                port_updates.append(port_id)
                raise neutron_client_exc.Forbidden()

        with mock.patch.object(
                self.neutron, "update_port",
                side_effect=fake_update_port) as mock_update_port:
            # let's trigger a heal
            result = self.cli.heal_allocations(verbose=True, max_count=2)
            self.assertEqual(5, mock_update_port.call_count)

        self._assert_placement_not_updated(server)

        # the order of the ports is random due to usage of dicts so we
        # need the info from the fake_update_port that which port update
        # failed
        # the first port update was successful, this will be the first port to
        # rollback too and the rollback will fail
        self._assert_port_updated(port_updates[0])
        # the second port update was successful, this will be the second port
        # to rollback which will succeed
        self._assert_port_not_updated(port_updates[1])
        # the third port was never updated successfully
        self._assert_port_not_updated(port_updates[2])

        output = self.output.getvalue()
        self.assertIn(
            'Rolling back port update',
            output)
        self.assertIn(
            'Failed to update neutron ports with allocation keys and the '
            'automatic rollback of the previously successful port updates '
            'also failed',
            output)
        # as we failed to roll back the first port update we instruct the user
        # to clean it up manually
        self.assertIn(
            "Make sure that the binding:profile.allocation key of the "
            "affected ports ['%s'] are manually cleaned in neutron"
            % port_updates[0],
            output)
        self.assertEqual(7, result)

    def test_heal_port_allocation_placement_unavailable_during_a_c(self):
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        # Simulate that placement is unavailable during the allocation
        # candidate query. The safe_connect decorator signals that via
        # returning None.
        with mock.patch(
            'nova.scheduler.client.report.SchedulerReportClient.'
            'get_allocation_candidates',
            return_value=None
        ):
            result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_not_updated(server)
        self._assert_ports_not_updated(ports)

        self.assertEqual(3, result)

    def test_heal_port_allocation_placement_unavailable_during_update(self):
        server, ports = self._create_server_with_missing_port_alloc(
            [self.neutron.port_1])

        # Simulate that placement is unavailable during updating the
        # allocation. The retry decorator signals that via returning False
        with mock.patch(
            'nova.scheduler.client.report.SchedulerReportClient.'
            'put_allocations',
            return_value=False
        ):
            result = self.cli.heal_allocations(verbose=True, max_count=2)

        self._assert_placement_not_updated(server)
        # Actually there was a port update but that was rolled back when
        # the allocation update failed
        self._assert_ports_not_updated(ports)

        output = self.output.getvalue()
        self.assertIn(
            'Rolling back port update',
            output)
        self.assertEqual(3, result)


class TestNovaManagePlacementHealPortAllocationsExtended(
    TestNovaManagePlacementHealPortAllocations
):
    """Run the same tests as in TestNovaManagePlacementHealPortAllocations but
    with the ExtendedResourceRequestNeutronFixture that automatically
    translates the resource request in the ports used by these test to the
    extended format. Note that this will test the extended format handling but
    only with a single request group per port.
    """

    def setUp(self):
        super().setUp()
        self.neutron = self.useFixture(
            test_res_req.ExtendedResourceRequestNeutronFixture(self))

    def _get_resource_request(self, port):
        # we assume a single resource request group in this test class
        res_req = port[constants.RESOURCE_REQUEST][constants.REQUEST_GROUPS]
        assert len(res_req) == 1
        return res_req[0]

    def _assert_port_updated(self, port_uuid):
        updated_port = self.neutron.show_port(port_uuid)['port']
        binding_profile = updated_port.get('binding:profile', {})
        self.assertEqual(
            {port_uuid: self.ovs_bridge_rp_per_host[self.compute1_rp_uuid]},
            binding_profile['allocation'])


class TestNovaManagePlacementHealPortAllocationsMultiGroup(
    TestNovaManagePlacementHealPortAllocations
):
    """Run the same tests as in TestNovaManagePlacementHealPortAllocations but
    with the MultiGroupResourceRequestNeutronFixture to test with extended
    resource request with multiple groups.
    """

    def setUp(self):
        super().setUp()
        self.neutron = self.useFixture(
            test_res_req.MultiGroupResourceRequestNeutronFixture(self))

    @staticmethod
    def _get_default_resource_request(port_uuid):
        # we need unique uuids per port for multi port tests
        g1 = getattr(uuids, port_uuid + "group1")
        g2 = getattr(uuids, port_uuid + "group2")
        return {
            "request_groups": [
                {
                    "id": g1,
                    "resources": {
                        orc.NET_BW_IGR_KILOBIT_PER_SEC: 1000,
                        orc.NET_BW_EGR_KILOBIT_PER_SEC: 1000},
                    "required": [
                        "CUSTOM_PHYSNET2", "CUSTOM_VNIC_TYPE_NORMAL"
                    ]
                },
                {
                    "id": g2,
                    "resources": {
                        orc.NET_PACKET_RATE_KILOPACKET_PER_SEC: 1000
                    },
                    "required": ["CUSTOM_VNIC_TYPE_NORMAL"]
                }
            ],
            "same_subtree": [g1, g2],
        }

    @staticmethod
    def _get_too_big_resource_request():
        # The port will request too much NET_BW_IGR_KILOBIT_PER_SEC so there is
        # no RP on the host that can provide it.
        return {
            "request_groups": [
                {
                    "id": uuids.g1,
                    "resources": {
                        orc.NET_BW_IGR_KILOBIT_PER_SEC: 10000000000000,
                        orc.NET_BW_EGR_KILOBIT_PER_SEC: 1000},
                    "required": [
                        "CUSTOM_PHYSNET2", "CUSTOM_VNIC_TYPE_NORMAL"
                    ]
                },
                {
                    "id": uuids.g2,
                    "resources": {
                        orc.NET_PACKET_RATE_KILOPACKET_PER_SEC: 1000
                    },
                    "required": ["CUSTOM_VNIC_TYPE_NORMAL"]
                }
            ],
            "same_subtree": [uuids.g1, uuids.g2],
        }

    @staticmethod
    def _get_ambiguous_resource_request():
        # ambiguity cannot really be simulated with multiple groups as that
        # would require multiple OVS bridges instead of multiple PFs. So
        # falling back to a single group in this specific test case.
        return {
            "request_groups": [
                {
                    "id": uuids.g1,
                    "resources": {
                        orc.NET_BW_IGR_KILOBIT_PER_SEC: 1000,
                        orc.NET_BW_EGR_KILOBIT_PER_SEC: 1000},
                    "required": [
                        "CUSTOM_PHYSNET2", "CUSTOM_VNIC_TYPE_DIRECT"
                    ]
                },
            ],
            "same_subtree": [uuids.g1],
        }

    def _assert_placement_updated(self, server, ports):
        rsp = self.placement.get(
            '/allocations/%s' % server['id'],
            version=1.28).body

        allocations = rsp['allocations']

        # we expect one allocation for the compute resources, one on the OVS
        # bridge RP due to bandwidth and one on the OVS agent RP due to packet
        # rate request
        self.assertEqual(3, len(allocations))
        self.assertEqual(
            self._resources_from_flavor(self.flavor),
            allocations[self.compute1_rp_uuid]['resources'])

        self.assertEqual(server['tenant_id'], rsp['project_id'])
        self.assertEqual(server['user_id'], rsp['user_id'])

        ovs_bridge_allocations = allocations[
            self.ovs_bridge_rp_per_host[self.compute1_rp_uuid]]['resources']
        ovs_agent_allocations = allocations[
            self.ovs_agent_rp_per_host[self.compute1_rp_uuid]]['resources']

        total_bandwidth_request = collections.defaultdict(int)
        total_packet_rate_request = collections.defaultdict(int)
        for port in ports:
            res_req = (port.get(constants.RESOURCE_REQUEST) or {})
            for group in res_req.get(constants.REQUEST_GROUPS):
                port_request = group['resources']
                for rc, amount in port_request.items():
                    if rc == orc.NET_PACKET_RATE_KILOPACKET_PER_SEC:
                        total_packet_rate_request[rc] += amount
                    else:
                        total_bandwidth_request[rc] += amount

        self.assertEqual(total_bandwidth_request, ovs_bridge_allocations)
        self.assertEqual(total_packet_rate_request, ovs_agent_allocations)

    def _assert_port_updated(self, port_uuid):
        updated_port = self.neutron.show_port(port_uuid)['port']
        binding_profile = updated_port.get('binding:profile', {})
        self.assertEqual(
            {
                getattr(uuids, port_uuid + "group1"):
                    self.ovs_bridge_rp_per_host[self.compute1_rp_uuid],
                getattr(uuids, port_uuid + "group2"):
                    self.ovs_agent_rp_per_host[self.compute1_rp_uuid],
            },
            binding_profile['allocation']
        )


class TestNovaManagePlacementSyncAggregates(
        integrated_helpers.ProviderUsageBaseTestCase):
    """Functional tests for nova-manage placement sync_aggregates"""

    # This is required by the parent class.
    compute_driver = 'fake.SmallFakeDriver'

    def setUp(self):
        super(TestNovaManagePlacementSyncAggregates, self).setUp()
        self.cli = manage.PlacementCommands()
        # Start two computes. At least two computes are useful for testing
        # to make sure removing one from an aggregate doesn't remove the other.
        self._start_compute('host1')
        self._start_compute('host2')
        # Make sure we have two hypervisors reported in the API.
        hypervisors = self.admin_api.api_get(
            '/os-hypervisors').body['hypervisors']
        self.assertEqual(2, len(hypervisors))
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

    def _create_aggregate(self, name):
        return self.admin_api.post_aggregate({'aggregate': {'name': name}})

    def test_sync_aggregates(self):
        """This is a simple test which does the following:

        - add each host to a unique aggregate
        - add both hosts to a shared aggregate
        - run sync_aggregates and assert both providers are in two aggregates
        - run sync_aggregates again and make sure nothing changed
        """
        # create three aggregates, one per host and one shared
        host1_agg = self._create_aggregate('host1')
        host2_agg = self._create_aggregate('host2')
        shared_agg = self._create_aggregate('shared')

        # Add the hosts to the aggregates. We have to temporarily mock out the
        # scheduler report client to *not* mirror the add host changes so that
        # sync_aggregates will do the job.
        with mock.patch('nova.scheduler.client.report.SchedulerReportClient.'
                        'aggregate_add_host'):
            self.admin_api.add_host_to_aggregate(host1_agg['id'], 'host1')
            self.admin_api.add_host_to_aggregate(host2_agg['id'], 'host2')
            self.admin_api.add_host_to_aggregate(shared_agg['id'], 'host1')
            self.admin_api.add_host_to_aggregate(shared_agg['id'], 'host2')

        # Run sync_aggregates and assert both providers are in two aggregates.
        result = self.cli.sync_aggregates(verbose=True)
        self.assertEqual(0, result, self.output.getvalue())

        host_to_rp_uuid = {}
        for host in ('host1', 'host2'):
            rp_uuid = self._get_provider_uuid_by_host(host)
            host_to_rp_uuid[host] = rp_uuid
            rp_aggregates = self._get_provider_aggregates(rp_uuid)
            self.assertEqual(2, len(rp_aggregates),
                             '%s should be in two provider aggregates' % host)
            self.assertIn(
                'Successfully added host (%s) and provider (%s) to aggregate '
                '(%s)' % (host, rp_uuid, shared_agg['uuid']),
                self.output.getvalue())

        # Remove host1 from the shared aggregate. Again, we have to temporarily
        # mock out the call from the aggregates API to placement to mirror the
        # change.
        with mock.patch('nova.scheduler.client.report.SchedulerReportClient.'
                        'aggregate_remove_host'):
            self.admin_api.remove_host_from_aggregate(
                shared_agg['id'], 'host1')

        # Run sync_aggregates and assert the provider for host1 is still in two
        # aggregates and host2's provider is still in two aggregates.
        # TODO(mriedem): When we add an option to remove providers from
        # placement aggregates when the corresponding host isn't in a compute
        # aggregate, we can test that the host1 provider is only left in one
        # aggregate.
        result = self.cli.sync_aggregates(verbose=True)
        self.assertEqual(0, result, self.output.getvalue())
        for host in ('host1', 'host2'):
            rp_uuid = host_to_rp_uuid[host]
            rp_aggregates = self._get_provider_aggregates(rp_uuid)
            self.assertEqual(2, len(rp_aggregates),
                             '%s should be in two provider aggregates' % host)


class TestNovaManagePlacementAudit(
        integrated_helpers.ProviderUsageBaseTestCase):
    """Functional tests for nova-manage placement audit"""

    # Let's just use a simple fake driver
    compute_driver = 'fake.SmallFakeDriver'

    def setUp(self):
        super(TestNovaManagePlacementAudit, self).setUp()
        self.cli = manage.PlacementCommands()
        # Make sure we have two computes for migrations
        self.compute1 = self._start_compute('host1')
        self.compute2 = self._start_compute('host2')

        # Make sure we have two hypervisors reported in the API.
        hypervisors = self.admin_api.api_get(
            '/os-hypervisors').body['hypervisors']
        self.assertEqual(2, len(hypervisors))

        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

        self.flavor = self.api.get_flavors()[0]

    def test_audit_orphaned_allocation_from_instance_delete(self):
        """Creates a server and deletes it by retaining its allocations so the
           audit command can find it.
        """
        target_hostname = self.compute1.host
        rp_uuid = self._get_provider_uuid_by_host(target_hostname)

        server = self._boot_and_check_allocations(self.flavor, target_hostname)

        # let's mock the allocation delete call to placement
        with mock.patch('nova.scheduler.client.report.SchedulerReportClient.'
                        'delete_allocation_for_instance'):
            self.api.delete_server(server['id'])
            self._wait_until_deleted(server)

        # make sure the allocation is still around
        self.assertFlavorMatchesUsage(rp_uuid, self.flavor)

        # Don't ask to delete the orphaned allocations, just audit them
        ret = self.cli.audit(verbose=True)
        # The allocation should still exist
        self.assertFlavorMatchesUsage(rp_uuid, self.flavor)

        output = self.output.getvalue()
        self.assertIn(
            'Allocations for consumer UUID %(consumer_uuid)s on '
            'Resource Provider %(rp_uuid)s can be deleted' %
            {'consumer_uuid': server['id'],
             'rp_uuid': rp_uuid},
            output)
        self.assertIn('Processed 1 allocation.', output)
        # Here we don't want to delete the found allocations
        self.assertNotIn(
            'Deleted allocations for consumer UUID %s' % server['id'], output)
        self.assertEqual(3, ret)

        # Now ask the audit command to delete the rogue allocations.
        ret = self.cli.audit(delete=True, verbose=True)

        # The allocations are now deleted
        self.assertRequestMatchesUsage(
            {'VCPU': 0, 'MEMORY_MB': 0, 'DISK_GB': 0}, rp_uuid)

        output = self.output.getvalue()
        self.assertIn(
            'Deleted allocations for consumer UUID %s' % server['id'], output)
        self.assertIn('Processed 1 allocation.', output)
        self.assertEqual(4, ret)

    def test_audit_orphaned_allocations_from_confirmed_resize(self):
        """Resize a server but when confirming it, leave the migration
           allocation there so the audit command can find it.
        """
        source_hostname = self.compute1.host
        dest_hostname = self.compute2.host

        source_rp_uuid = self._get_provider_uuid_by_host(source_hostname)
        dest_rp_uuid = self._get_provider_uuid_by_host(dest_hostname)

        old_flavor = self.flavor
        new_flavor = self.api.get_flavors()[1]
        # we want to make sure we resize to compute2
        self.flags(allow_resize_to_same_host=False)

        server = self._boot_and_check_allocations(self.flavor, source_hostname)

        # Do a resize
        post = {
            'resize': {
                'flavorRef': new_flavor['id']
            }
        }
        self._move_and_check_allocations(
            server, request=post, old_flavor=old_flavor,
            new_flavor=new_flavor, source_rp_uuid=source_rp_uuid,
            dest_rp_uuid=dest_rp_uuid)

        # Retain the migration UUID record for later usage
        migration_uuid = self.get_migration_uuid_for_instance(server['id'])

        # Confirm the resize so it should in theory delete the source
        # allocations but mock out the allocation delete for the source
        post = {'confirmResize': None}
        with mock.patch('nova.scheduler.client.report.SchedulerReportClient.'
                        'delete_allocation_for_instance'):
            self.api.post_server_action(
                server['id'], post, check_response_status=[204])
            self._wait_for_state_change(server, 'ACTIVE')

        # The target host usage should be according to the new flavor...
        self.assertFlavorMatchesUsage(dest_rp_uuid, new_flavor)
        # ...but we should still see allocations for the source compute
        self.assertFlavorMatchesUsage(source_rp_uuid, old_flavor)

        # Now, run the audit command that will find this orphaned allocation
        ret = self.cli.audit(verbose=True)
        output = self.output.getvalue()
        self.assertIn(
            'Allocations for consumer UUID %(consumer_uuid)s on '
            'Resource Provider %(rp_uuid)s can be deleted' %
            {'consumer_uuid': migration_uuid, 'rp_uuid': source_rp_uuid},
            output)
        self.assertIn('Processed 1 allocation.', output)
        self.assertEqual(3, ret)

        # Now we want to delete the orphaned allocation that is duplicate
        ret = self.cli.audit(delete=True, verbose=True)

        # There should be no longer usage for the source host since the
        # allocation disappeared
        self.assertRequestMatchesUsage({'VCPU': 0,
                                        'MEMORY_MB': 0,
                                        'DISK_GB': 0}, source_rp_uuid)

        output = self.output.getvalue()
        self.assertIn(
            'Deleted allocations for consumer UUID %(consumer_uuid)s on '
            'Resource Provider %(rp_uuid)s' %
            {'consumer_uuid': migration_uuid,
             'rp_uuid': source_rp_uuid},
            output)
        self.assertIn('Processed 1 allocation.', output)
        self.assertEqual(4, ret)


class TestDBArchiveDeletedRows(integrated_helpers._IntegratedTestBase):
    """Functional tests for the "nova-manage db archive_deleted_rows" CLI."""
    api_major_version = 'v2.1'

    def setUp(self):
        super(TestDBArchiveDeletedRows, self).setUp()
        self.enforce_fk_constraints()
        self.cli = manage.DbCommands()
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

    def test_archive_instance_group_members(self):
        """Tests that instance_group_member records in the API DB are deleted
        when a server group member instance is archived.
        """
        # Create a server group.
        group = self.api.post_server_groups(
            {'name': 'test_archive_instance_group_members',
             'policies': ['affinity']})
        # Create two servers in the group.
        server = self._build_server()
        server['min_count'] = 2
        server_req = {
            'server': server, 'os:scheduler_hints': {'group': group['id']}}
        # Since we don't pass return_reservation_id=True we get the first
        # server back in the response. We're also using the CastAsCallFixture
        # (from the base class) fixture so we don't have to worry about the
        # server being ACTIVE.
        server = self.api.post_server(server_req)
        # Assert we have two group members.
        self.assertEqual(
            2, len(self.api.get_server_group(group['id'])['members']))
        # Now delete one server and then we can archive.
        server = self.api.get_server(server['id'])
        self._delete_server(server)
        # Now archive.
        self.cli.archive_deleted_rows(verbose=True)
        # Assert only one instance_group_member record was deleted.
        self.assertRegex(self.output.getvalue(),
                         r".*instance_group_member.*\| 1.*")
        # And that we still have one remaining group member.
        self.assertEqual(
            1, len(self.api.get_server_group(group['id'])['members']))


class TestDBArchiveDeletedRowsTaskLog(integrated_helpers._IntegratedTestBase):
    """Functional tests for the
    "nova-manage db archive_deleted_rows --task-log" CLI.
    """
    api_major_version = 'v2.1'

    def setUp(self):
        # Override time to ensure we cross audit period boundaries in a
        # predictable way.
        self.faketoday = datetime.datetime(2021, 7, 1)
        # This needs to be done before setUp() starts services, else they will
        # be considered "down" by the ComputeFilter.
        self.useFixture(test.TimeOverride(override_time=self.faketoday))
        super(TestDBArchiveDeletedRowsTaskLog, self).setUp()
        self.enforce_fk_constraints()
        self.cli = manage.DbCommands()
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

    def test_archive_task_logs(self):
        # Enable the generation of task_log records by the instance usage audit
        # nova-compute periodic task.
        self.flags(instance_usage_audit=True)
        compute = self.computes['compute']

        # Create a few servers for the periodic task to process.
        for i in range(0, 3):
            self._create_server()

        ctxt = context.get_admin_context()

        # The instance usage audit periodic task only processes servers that
        # were active during the last audit period. The audit period defaults
        # to 1 month, so the last audit period would be the previous calendar
        # month. Advance time one month, two months, and three months to
        # generate a task_log record for the servers we created, for each of
        # three audit periods.
        # July has 31 days, August has 31 days, September has 30 days.
        for days in (31, 31 + 31, 31 + 31 + 30):
            future = timeutils.utcnow() + datetime.timedelta(days=days)
            timeutils.set_time_override(future)
            # task_log records are generated by the _instance_usage_audit
            # periodic task.
            compute.manager._instance_usage_audit(ctxt)
            # Audit period defaults to 1 month, the last audit period will
            # be the previous calendar month.
            begin, end = nova_utils.last_completed_audit_period()
            # Verify that we have 1 task_log record per audit period.
            task_logs = objects.TaskLogList.get_all(
                ctxt, 'instance_usage_audit', begin, end)
            self.assertEqual(1, len(task_logs))
            # Restore original time override.
            timeutils.set_time_override(self.faketoday)

        # First try archiving without --task-log. Expect no task_log entries in
        # the results.
        self.cli.archive_deleted_rows(verbose=True)
        self.assertNotIn('task_log', self.output.getvalue())
        # Next try archiving with --task-log and --before.
        # We'll archive records that were last updated before the second audit
        # period.
        # The task_log records were created/updated on 2021-08-01, 2021-09-01,
        # and 2021-10-01. So to archive one record, we need to use
        # before > 2021-08-01. 2021-07-01 + 31 + 1 = 2021-08-02
        before = timeutils.utcnow() + datetime.timedelta(days=31 + 1)
        self.cli.archive_deleted_rows(
            task_log=True, before=before.isoformat(), verbose=True)
        # Verify that only 1 task_log record was archived.
        self.assertRegex(self.output.getvalue(), r'\| task_log\s+\| 1')
        # Now archive all of the rest, there should be 2 left.
        self.cli.archive_deleted_rows(task_log=True, verbose=True)
        self.assertRegex(self.output.getvalue(), r'\| task_log\s+\| 2')

    def test_archive_before(self):
        """Test that no records are left over after archiving with --before"""
        # Create and delete a server so we can archive.
        server = self._build_server()
        server = self.api.post_server({'server': server})
        server = self.api.get_server(server['id'])
        self._delete_server(server)
        # First try archiving records before a past datetime. Nothing should be
        # archived.
        past = timeutils.utcnow() - datetime.timedelta(hours=1)
        ret = self.cli.archive_deleted_rows(before=past.isoformat())
        # Return code 0 means nothing was archived.
        self.assertEqual(0, ret)
        # Now try archiving records before a future datetime. Everything should
        # have been archived.
        future = timeutils.utcnow() + datetime.timedelta(hours=1)
        ret = self.cli.archive_deleted_rows(before=future.isoformat())
        # Return code 1 means something was archived.
        self.assertEqual(1, ret)
        # Now archive everything without specifying --before.
        ret = self.cli.archive_deleted_rows()
        # Return code 0 means nothing was archived.
        self.assertEqual(0, ret)


class TestDBArchiveDeletedRowsMultiCell(integrated_helpers.InstanceHelperMixin,
                                        test.TestCase):

    NUMBER_OF_CELLS = 2

    def setUp(self):
        super(TestDBArchiveDeletedRowsMultiCell, self).setUp()
        self.enforce_fk_constraints()
        self.useFixture(nova_fixtures.NeutronFixture(self))
        self.useFixture(nova_fixtures.GlanceFixture(self))
        self.useFixture(func_fixtures.PlacementFixture())

        api_fixture = self.useFixture(nova_fixtures.OSAPIFixture(
            api_version='v2.1'))
        # We need the admin api to forced_host for server create
        self.api = api_fixture.admin_api

        self.start_service('conductor')
        self.start_service('scheduler')

        self.context = context.RequestContext('fake-user', 'fake-project')
        self.cli = manage.DbCommands()
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

        # Start two compute services, one per cell
        self.compute1 = self.start_service('compute', host='host1',
                                           cell_name='cell1')
        self.compute2 = self.start_service('compute', host='host2',
                                           cell_name='cell2')

    def test_archive_deleted_rows(self):
        admin_context = context.get_admin_context(read_deleted='yes')
        server_ids_by_cell = collections.defaultdict(list)
        # Create two servers per cell to make sure archive for table iterates
        # at least once.
        for i in range(2):
            # Boot a server to cell1
            server = self._build_server(az='nova:host1')
            created_server = self.api.post_server({'server': server})
            self._wait_for_state_change(created_server, 'ACTIVE')
            server_ids_by_cell['cell1'].append(created_server['id'])
            # Boot a server to cell2
            server = self._build_server(az='nova:host2')
            created_server = self.api.post_server({'server': server})
            self._wait_for_state_change(created_server, 'ACTIVE')
            server_ids_by_cell['cell2'].append(created_server['id'])
            # Boot a server to cell0 (cause ERROR state prior to schedule)
            server = self._build_server()
            # Flavor m1.xlarge cannot be fulfilled
            server['flavorRef'] = 'http://fake.server/5'
            created_server = self.api.post_server({'server': server})
            self._wait_for_state_change(created_server, 'ERROR')
            server_ids_by_cell['cell0'].append(created_server['id'])

        # Verify all the servers are in the databases
        for cell_name, server_ids in server_ids_by_cell.items():
            for server_id in server_ids:
                with context.target_cell(
                    admin_context,
                    self.cell_mappings[cell_name]
                ) as cctxt:
                    objects.Instance.get_by_uuid(cctxt, server_id)
        # Delete the servers
        for cell_name, server_ids in server_ids_by_cell.items():
            for server_id in server_ids:
                self.api.delete_server(server_id)
        # Verify all the servers are in the databases still (as soft deleted)
        for cell_name, server_ids in server_ids_by_cell.items():
            for server_id in server_ids:
                with context.target_cell(
                    admin_context,
                    self.cell_mappings[cell_name]
                ) as cctxt:
                    objects.Instance.get_by_uuid(cctxt, server_id)
        # Archive the deleted rows
        self.cli.archive_deleted_rows(verbose=True, all_cells=True)
        # 6 instances should have been archived (cell0, cell1, cell2)
        self.assertRegex(self.output.getvalue(),
                         r"\| cell0\.instances\s+\| 2")
        self.assertRegex(self.output.getvalue(),
                         r"\| cell1\.instances\s+\| 2")
        self.assertRegex(self.output.getvalue(),
                         r"\| cell2\.instances\s+\| 2")
        self.assertRegex(self.output.getvalue(),
                         r"\| API_DB\.instance_mappings\s+\| 6")
        self.assertRegex(self.output.getvalue(),
                         r"\| API_DB\.request_specs\s+\| 6")
        # Verify all the servers are gone from the cell databases
        for cell_name, server_ids in server_ids_by_cell.items():
            for server_id in server_ids:
                with context.target_cell(
                    admin_context,
                    self.cell_mappings[cell_name]
                ) as cctxt:
                    self.assertRaises(exception.InstanceNotFound,
                                      objects.Instance.get_by_uuid,
                                      cctxt, server_id)


class TestDBArchiveDeletedRowsMultiCellTaskLog(
        integrated_helpers.InstanceHelperMixin, test.TestCase):
    """Functional tests for the "nova-manage db archive_deleted_rows
    --all-cells --task-log" CLI.
    """
    NUMBER_OF_CELLS = 2

    def setUp(self):
        # Override time to ensure we cross audit period boundaries in a
        # predictable way.
        self.faketoday = datetime.datetime(2021, 7, 1)
        # This needs to be done before setUp() starts services, else they will
        # be considered "down" by the ComputeFilter.
        self.useFixture(test.TimeOverride(override_time=self.faketoday))
        super(TestDBArchiveDeletedRowsMultiCellTaskLog, self).setUp()
        self.enforce_fk_constraints()
        self.useFixture(nova_fixtures.NeutronFixture(self))
        self.useFixture(nova_fixtures.GlanceFixture(self))
        self.useFixture(func_fixtures.PlacementFixture())

        api_fixture = self.useFixture(nova_fixtures.OSAPIFixture(
            api_version='v2.1'))
        # We need the admin api to forced_host for server create
        self.api = api_fixture.admin_api

        self.start_service('conductor')
        self.start_service('scheduler')

        self.context = context.RequestContext('fake-user', 'fake-project')
        self.cli = manage.DbCommands()
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

        # Start two compute services, one per cell
        self.compute1 = self.start_service('compute', host='host1',
                                           cell_name='cell1')
        self.compute2 = self.start_service('compute', host='host2',
                                           cell_name='cell2')

    def test_archive_task_logs(self):
        # Enable the generation of task_log records by the instance usage audit
        # nova-compute periodic task.
        self.flags(instance_usage_audit=True)

        # Create servers for the periodic task to process.
        # Boot a server to cell1
        server = self._build_server(az='nova:host1')
        created_server = self.api.post_server({'server': server})
        self._wait_for_state_change(created_server, 'ACTIVE')
        # Boot a server to cell2
        server = self._build_server(az='nova:host2')
        created_server = self.api.post_server({'server': server})
        self._wait_for_state_change(created_server, 'ACTIVE')

        ctxt = context.get_admin_context()

        # The instance usage audit periodic task only processes servers that
        # were active during the last audit period. The audit period defaults
        # to 1 month, so the last audit period would be the previous calendar
        # month. Advance time one month, two months, and three months to
        # generate a task_log record for the servers we created, for each of
        # three audit periods.
        # July has 31 days, August has 31 days, September has 30 days.
        for days in (31, 31 + 31, 31 + 31 + 30):
            future = timeutils.utcnow() + datetime.timedelta(days=days)
            timeutils.set_time_override(future)
            # task_log records are generated by the _instance_usage_audit
            # periodic task.
            with context.target_cell(
                    ctxt, self.cell_mappings['cell1']) as cctxt:
                self.compute1.manager._instance_usage_audit(cctxt)
            with context.target_cell(
                    ctxt, self.cell_mappings['cell2']) as cctxt:
                self.compute2.manager._instance_usage_audit(ctxt)
            # Audit period defaults to 1 month, the last audit period will
            # be the previous calendar month.
            begin, end = nova_utils.last_completed_audit_period()
            # Restore original time override.
            timeutils.set_time_override(self.faketoday)

            for cell_name in ('cell1', 'cell2'):
                with context.target_cell(
                        ctxt, self.cell_mappings[cell_name]) as cctxt:
                    task_logs = objects.TaskLogList.get_all(
                        cctxt, 'instance_usage_audit', begin, end)
                    self.assertEqual(1, len(task_logs))

        # First try archiving without --task-log. Expect no task_log entries in
        # the results.
        self.cli.archive_deleted_rows(all_cells=True, verbose=True)
        self.assertNotIn('task_log', self.output.getvalue())
        # Next try archiving with --task-log and --before.
        # We'll archive records that were last updated before the second audit
        # period.
        # The task_log records were created/updated on 2021-08-01, 2021-09-01,
        # and 2021-10-01. So to archive one record, we need to use
        # before > 2021-08-01. 2021-07-01 + 31 + 1 = 2021-08-02
        before = timeutils.utcnow() + datetime.timedelta(days=31 + 1)
        self.cli.archive_deleted_rows(
            all_cells=True, task_log=True, before=before.isoformat(),
            verbose=True)
        # Verify that only 2 task_log records were archived, 1 in each cell.
        for cell_name in ('cell1', 'cell2'):
            self.assertRegex(
                self.output.getvalue(), r'\| %s.task_log\s+\| 1' % cell_name)
        # Now archive all of the rest, there should be 4 left, 2 in each cell.
        self.cli.archive_deleted_rows(
            all_cells=True, task_log=True, verbose=True)
        for cell_name in ('cell1', 'cell2'):
            self.assertRegex(
                self.output.getvalue(), r'\| %s.task_log\s+\| 2' % cell_name)


class TestNovaManageLimits(integrated_helpers.ProviderUsageBaseTestCase):

    # This is required by the parent class.
    compute_driver = 'fake.MediumFakeDriver'
    NUMBER_OF_CELLS = 2

    def setUp(self):
        super().setUp()
        self.ctxt = context.get_admin_context()
        self.cli = manage.LimitsCommands()
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))
        self.ul_api = self.useFixture(nova_fixtures.UnifiedLimitsFixture())
        # Start two compute services, one per cell
        self.compute1 = self.start_service('compute', host='host1',
                                           cell_name='cell1')
        self.compute2 = self.start_service('compute', host='host2',
                                           cell_name='cell2')

    @mock.patch('nova.quota.QUOTAS.get_defaults')
    def test_migrate_to_unified_limits_no_db_access(self, mock_get_defaults):
        mock_get_defaults.side_effect = oslo_db_exc.CantStartEngineError()
        return_code = self.cli.migrate_to_unified_limits(verbose=True)
        self.assertEqual(2, return_code)

    @mock.patch('nova.utils.get_sdk_adapter')
    def test_migrate_to_unified_limits_unexpected_error(self, mock_sdk):
        # Simulate an error creating limits.
        mock_sdk.return_value.create_registered_limit.side_effect = (
            test.TestingException('oops!'))
        mock_sdk.return_value.create_limit.side_effect = (
            test.TestingException('oops!'))

        # Create a few project limits.
        objects.Quotas.create_limit(self.ctxt, uuids.project, 'ram', 8192)
        objects.Quotas.create_limit(self.ctxt, uuids.project, 'instances', 25)
        objects.Quotas.create_limit(self.ctxt, uuids.project, 'cores', 22)

        return_code = self.cli.migrate_to_unified_limits(
            project_id=uuids.project, verbose=True)
        self.assertEqual(1, return_code)

        # Verify that limit create attempts for other resources were attempted
        # after an unexpected error.
        #
        # There are 10 default limit values in the config options: instances,
        # cores, ram, metadata_items, injected_files,
        # injected_file_content_bytes, injected_file_path_length, key_pairs,
        # server_groups, and server_group_members.
        #
        # And there is 1 default limit value automatically generated for PCPU
        # based on 'cores'.
        self.assertEqual(
            11, mock_sdk.return_value.create_registered_limit.call_count)

        # We expect that we attempted to create 4 project limits:
        # class:MEMORY_MB, servers, and class:VCPU = 3 + special case
        # class:PCPU = 4.
        self.assertEqual(4, mock_sdk.return_value.create_limit.call_count)

    def test_migrate_to_unified_limits_already_exists(self):
        # Create a couple of unified limits to already exist.
        self.ul_api.create_registered_limit(
            resource_name='servers', default_limit=8)
        self.ul_api.create_limit(
            resource_name='class:VCPU', resource_limit=6,
            project_id=uuids.project)

        # Create a couple of project limits.
        objects.Quotas.create_limit(self.ctxt, uuids.project, 'cores', 10)
        objects.Quotas.create_limit(self.ctxt, uuids.project, 'instances', 25)

        self.cli.migrate_to_unified_limits(
            project_id=uuids.project, verbose=True)

        # There are 10 default limit values in the config options +
        # 1 special case for PCPU which will be added based on VCPU = 11.
        # Because a limit for 'servers' already exists, we should have only
        # created 10.
        mock_sdk = self.ul_api.mock_sdk_adapter
        self.assertEqual(
            10, mock_sdk.create_registered_limit.call_count)

        # There already exists a project limit for 'class:VCPU', so we should
        # have created only 2 project limits. One for 'servers' and one for
        # special case 'class:PCPU' generated from VCPU.
        self.assertEqual(2, mock_sdk.create_limit.call_count)

    def test_migrate_to_unified_limits(self):
        # Set some defaults using the config options.
        self.flags(instances=5, group='quota')
        self.flags(cores=22, group='quota')
        self.flags(ram=4096, group='quota')
        self.flags(metadata_items=64, group='quota')
        self.flags(injected_files=3, group='quota')
        self.flags(injected_file_content_bytes=9 * 1024, group='quota')
        self.flags(injected_file_path_length=250, group='quota')
        self.flags(key_pairs=50, group='quota')
        self.flags(server_groups=7, group='quota')
        self.flags(server_group_members=12, group='quota')
        # Create a couple of defaults via the 'default' quota class. These take
        # precedence over the config option values.
        objects.Quotas.create_class(self.ctxt, 'default', 'cores', 10)
        objects.Quotas.create_class(self.ctxt, 'default', 'key_pairs', 75)
        # Create obsolete limits which should not be migrated to unified
        # limits.
        objects.Quotas.create_class(self.ctxt, 'default', 'fixed_ips', 8)
        objects.Quotas.create_class(self.ctxt, 'default', 'floating_ips', 6)
        objects.Quotas.create_class(self.ctxt, 'default', 'security_groups', 4)
        objects.Quotas.create_class(
            self.ctxt, 'default', 'security_group_rules', 14)
        # Create a couple of project limits.
        objects.Quotas.create_limit(self.ctxt, uuids.project, 'ram', 8192)
        objects.Quotas.create_limit(self.ctxt, uuids.project, 'instances', 25)

        # Verify there are no unified limits yet.
        registered_limits = list(self.ul_api.registered_limits())
        self.assertEqual(0, len(registered_limits))
        limits = list(self.ul_api.limits(project_id=uuids.project))
        self.assertEqual(0, len(limits))

        # Verify that --dry-run works to not actually create limits.
        self.cli.migrate_to_unified_limits(dry_run=True)

        # There should still be no unified limits yet.
        registered_limits = list(self.ul_api.registered_limits())
        self.assertEqual(0, len(registered_limits))
        limits = list(self.ul_api.limits(project_id=uuids.project))
        self.assertEqual(0, len(limits))

        # Migrate the limits.
        self.cli.migrate_to_unified_limits(
            project_id=uuids.project, verbose=True)

        # There are 10 default limit values in the config options +
        # 1 special case for PCPU which will be added based on VCPU = 11.
        #
        # There should be 11 registered (default) limits now.
        expected_registered_limits = {
            'servers': 5,
            'class:VCPU': 10,
            'class:PCPU': 10,
            'class:MEMORY_MB': 4096,
            'server_metadata_items': 64,
            'server_injected_files': 3,
            'server_injected_file_content_bytes': 9 * 1024,
            'server_injected_file_path_bytes': 250,
            'server_key_pairs': 75,
            'server_groups': 7,
            'server_group_members': 12,
        }

        registered_limits = list(self.ul_api.registered_limits())
        self.assertEqual(11, len(registered_limits))
        for rl in registered_limits:
            self.assertEqual(
                expected_registered_limits[rl.resource_name], rl.default_limit)

        # And 2 project limits.
        expected_limits = {
            'class:MEMORY_MB': 8192,
            'servers': 25,
        }

        limits = list(self.ul_api.limits(project_id=uuids.project))
        self.assertEqual(2, len(limits))
        for pl in limits:
            self.assertEqual(
                expected_limits[pl.resource_name], pl.resource_limit)

        # Verify there are no project limits for a different project.
        other_project_limits = list(self.ul_api.limits(
            project_id=uuids.otherproject))
        self.assertEqual(0, len(other_project_limits))

        # Try migrating limits for a specific region.
        region_registered_limits = list(self.ul_api.registered_limits(
            region_id=uuids.region))
        self.assertEqual(0, len(region_registered_limits))

        result = self.cli.migrate_to_unified_limits(
            region_id=uuids.region, verbose=True)

        # There is a missing registered limit for class:DISK_GB.
        self.assertEqual(3, result)

        region_registered_limits = list(self.ul_api.registered_limits(
            region_id=uuids.region))
        self.assertEqual(11, len(region_registered_limits))
        for rl in region_registered_limits:
            self.assertEqual(
                expected_registered_limits[rl.resource_name], rl.default_limit)

        # Create a registered limit for class:DISK_GB.
        self.ul_api.create_registered_limit(
            resource_name='class:DISK_GB', default_limit=10)

        # Try migrating project limits for that region.
        region_limits = list(self.ul_api.limits(
            project_id=uuids.project, region_id=uuids.region))
        self.assertEqual(0, len(region_limits))

        self.cli.migrate_to_unified_limits(
            project_id=uuids.project, region_id=uuids.region, verbose=True)

        region_limits = list(self.ul_api.limits(
            project_id=uuids.project, region_id=uuids.region))
        self.assertEqual(2, len(region_limits))
        for pl in region_limits:
            self.assertEqual(
                expected_limits[pl.resource_name], pl.resource_limit)

        # Verify no --verbose outputs nothing, migrate limits for a different
        # project after clearing stdout.
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

        # Create a limit for the other project.
        objects.Quotas.create_limit(self.ctxt, uuids.otherproject, 'ram', 2048)

        result = self.cli.migrate_to_unified_limits(
            project_id=uuids.otherproject)

        other_project_limits = list(self.ul_api.limits(
            project_id=uuids.otherproject))
        self.assertEqual(1, len(other_project_limits))

        # Output should show success after migrating.
        self.assertIn('SUCCESS', self.output.getvalue())
        self.assertEqual(0, result)

    def _add_to_inventory(self, resource):
        # Add resource to inventory for both computes.
        for rp in self._get_all_providers():
            inv = self._get_provider_inventory(rp['uuid'])
            inv[resource] = {'total': 10}
            self._update_inventory(
                rp['uuid'], {'inventories': inv,
                'resource_provider_generation': rp['generation']})

    def _create_flavor_and_add_to_inventory(self, resource):
        # Create a flavor for the resource.
        flavor_id = self._create_flavor(
            vcpu=1, memory_mb=512, disk=1, ephemeral=0,
            extra_spec={f'resources:{resource}': 1})
        self._add_to_inventory(resource)
        return flavor_id

    def test_migrate_to_unified_limits_flavor_scanning(self):
        # Create a few flavors in the API database.
        for resource in ('NUMA_CORE', 'PCPU', 'NUMA_SOCKET'):
            self._create_flavor(
                vcpu=1, memory_mb=512, disk=1, ephemeral=0,
                extra_spec={f'resources:{resource}': 1})

        # Create a few instances with embedded flavors that are *not* in the
        # API database.
        self._create_resource_class('CUSTOM_BAREMETAL_SMALL')

        # Create servers on both computes (and cells).
        hosts = ('host1', 'host2')

        for i, resource in enumerate(
                ('VGPU', 'CUSTOM_BAREMETAL_SMALL', 'PGPU')):
            flavor_id = self._create_flavor_and_add_to_inventory(resource)

            # Create servers on both computes (and thus cells) and two
            # projects: nova.tests.fixtures.nova.PROJECT_ID and 'other'.
            server = self._create_server(
                flavor_id=flavor_id, host=hosts[i % 2], networks='none')

            # Delete the flavor so it can only be detected by scanning
            # embedded flavors.
            self._delete_flavor(flavor_id)

        # Delete the last instance which has resources:PGPU. It should not be
        # included because the instance is deleted.
        self._delete_server(server)

        result = self.cli.migrate_to_unified_limits()

        # PCPU will have had a registered limit created for it based on VCPU,
        # so it should also not be included in the list.
        self.assertIn('WARNING', self.output.getvalue())
        self.assertIn('class:CUSTOM_BAREMETAL_SMALL', self.output.getvalue())
        self.assertIn('class:DISK_GB', self.output.getvalue())
        self.assertIn('class:NUMA_CORE', self.output.getvalue())
        self.assertIn('class:NUMA_SOCKET', self.output.getvalue())
        self.assertIn('class:VGPU', self.output.getvalue())
        self.assertEqual(5, self.output.getvalue().count('class:'))
        self.assertEqual(3, result)

        # Now create registered limits for all of the resources in the list.
        resources = (
            'CUSTOM_BAREMETAL_SMALL', 'DISK_GB', 'NUMA_CORE', 'NUMA_SOCKET',
            'VGPU')
        for resource in resources:
            self.ul_api.create_registered_limit(
                resource_name='class:' + resource, default_limit=10)

        # Reset the output and run the migrate command again.
        self.output = StringIO()
        self.useFixture(fixtures.MonkeyPatch('sys.stdout', self.output))

        result = self.cli.migrate_to_unified_limits()

        # The output should be the success message because there are no longer
        # any resources missing registered limits.
        self.assertIn('SUCCESS', self.output.getvalue())
        # Return code should be 0 for success.
        self.assertEqual(0, result)

    def test_migrate_to_unified_limits_flavor_scanning_resource_request(self):
        # Create one server that has extra specs that will get translated into
        # resource classes.
        extra_spec = {
            'hw:mem_encryption': 'true',
            'hw:cpu_policy': 'dedicated',
        }
        flavor_id = self._create_flavor(
            name='fakeflavor', vcpu=1, memory_mb=512, disk=1, ephemeral=0,
            extra_spec=extra_spec)
        self._add_to_inventory('MEM_ENCRYPTION_CONTEXT')
        image_id = self._create_image(
            metadata={'hw_firmware_type': 'uefi'})['id']
        self._create_server(
            flavor_id=flavor_id, networks='none', image_uuid=image_id)

        result = self.cli.migrate_to_unified_limits()

        # FIXME(melwitt): Update this to remove the exception messages and add
        # class:MEM_ENCRYPTION_CONTEXT to the table when
        # https://bugs.launchpad.net/nova/+bug/2088831 is fixed.
        # Message is output two times: one for API database scan and one for
        # embedded flavor scan.
        self.assertEqual(2, self.output.getvalue().count('exception'))
        self.assertIn('WARNING', self.output.getvalue())
        self.assertIn('class:DISK_GB', self.output.getvalue())
        self.assertEqual(1, self.output.getvalue().count('class:'))
        self.assertEqual(3, result)

    def test_migrate_to_unified_limits_flavor_scanning_project(self):
        # Create a client that uses a different project.
        other_api = api_client.TestOpenStackClient(
            'other', self.api.base_url, project_id='other',
            roles=['reader', 'member'])
        other_api.microversion = '2.74'

        self._create_resource_class('CUSTOM_GOLD')
        apis = (self.api, other_api)

        for i, resource in enumerate(('VGPU', 'CUSTOM_GOLD')):
            flavor_id = self._create_flavor_and_add_to_inventory(resource)

            # Create servers for two projects:
            # nova.tests.fixtures.nova.PROJECT_ID and 'other'.
            self._create_server(
                flavor_id=flavor_id, api=apis[i % 2], networks='none')

            # Delete the flavor so it can only be detected by scanning embedded
            # flavors.
            self._delete_flavor(flavor_id)

        # Scope the command to project 'other'. This should cause
        # VGPU to not be detected in the embedded flavors.
        result = self.cli.migrate_to_unified_limits(project_id='other')

        # DISK_GB will also be found because it's a known standard resource
        # class that we know will be allocated.
        self.assertIn('WARNING', self.output.getvalue())
        self.assertIn('class:CUSTOM_GOLD', self.output.getvalue())
        self.assertIn('class:DISK_GB', self.output.getvalue())
        self.assertEqual(2, self.output.getvalue().count('class:'))
        self.assertEqual(3, result)

    @mock.patch.object(
        manage.LimitsCommands, '_get_resources_from_embedded_flavors',
        new=mock.NonCallableMock())
    def test_migrate_to_unified_limits_no_embedded_flavor_scan(self):
        # Create a few flavors in the API database.
        for resource in ('NUMA_CORE', 'PCPU', 'NUMA_SOCKET'):
            self._create_flavor(
                vcpu=1, memory_mb=512, disk=1, ephemeral=0,
                extra_spec={f'resources:{resource}': 1})

        # Create a few instances with embedded flavors that are *not* in the
        # API database.
        self._create_resource_class('CUSTOM_BAREMETAL_SMALL')

        # Create servers on both computes (and cells).
        hosts = ('host1', 'host2')

        for i, resource in enumerate(
                ('VGPU', 'CUSTOM_BAREMETAL_SMALL', 'PGPU')):
            flavor_id = self._create_flavor_and_add_to_inventory(resource)

            # Create servers on both computes (and thus cells) and two
            # projects: nova.tests.fixtures.nova.PROJECT_ID and 'other'.
            self._create_server(
                flavor_id=flavor_id, host=hosts[i % 2], networks='none')

            # Delete the flavor so it can only be detected by scanning embedded
            # flavors.
            self._delete_flavor(flavor_id)

        result = self.cli.migrate_to_unified_limits(
            no_embedded_flavor_scan=True)

        # VGPU, CUSTOM_BAREMETAL_SMALL, and PGPU should not be included in the
        # output because the embedded flavor scan should have been skipped.
        self.assertIn('WARNING', self.output.getvalue())
        self.assertIn('class:DISK_GB', self.output.getvalue())
        self.assertIn('class:NUMA_CORE', self.output.getvalue())
        self.assertIn('class:NUMA_SOCKET', self.output.getvalue())
        self.assertEqual(3, self.output.getvalue().count('class:'))
        self.assertEqual(3, result)

    def test_migrate_to_unified_limits_flavor_scanning_down_cell(self):
        # Fake a down cell returned from the instance list.
        real_get_instance_objects_sorted = (
            list_instances.get_instance_objects_sorted)

        def fake_get_instance_objects_sorted(*args, **kwargs):
            instances, down_cells = real_get_instance_objects_sorted(
                *args, **kwargs)
            return instances, [uuids.down_cell]

        self.useFixture(fixtures.MockPatchObject(
            list_instances, 'get_instance_objects_sorted',
            fake_get_instance_objects_sorted))

        self._create_resource_class('CUSTOM_GOLD')

        for i, resource in enumerate(('VGPU', 'CUSTOM_GOLD')):
            flavor_id = self._create_flavor_and_add_to_inventory(resource)

            # Create servers for two projects:
            # nova.tests.fixtures.nova.PROJECT_ID and 'other'.
            self._create_server(flavor_id=flavor_id, networks='none')

            # Delete the flavor so it can only be detected by scanning embedded
            # flavors.
            self._delete_flavor(flavor_id)

        result = self.cli.migrate_to_unified_limits()

        # DISK_GB will also be found because it's a known standard resource
        # class that we know will be allocated.
        self.assertIn('WARNING', self.output.getvalue())
        self.assertIn("Cells {'%s'}" % uuids.down_cell, self.output.getvalue())
        self.assertIn('class:CUSTOM_GOLD', self.output.getvalue())
        self.assertIn('class:DISK_GB', self.output.getvalue())
        self.assertIn('class:VGPU', self.output.getvalue())
        self.assertEqual(3, self.output.getvalue().count('class:'))
        self.assertEqual(3, result)
