# Copyright 2011 OpenStack Foundation
# Copyright 2013 IBM Corp.
#
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

from unittest import mock

from nova.api.openstack import api_version_request
from nova.api.openstack import common
from nova.api.openstack.compute import lock_server
from nova import exception
from nova.tests.unit.api.openstack.compute import admin_only_action_common
from nova.tests.unit import fake_instance


class LockServerTests(admin_only_action_common.CommonTests):

    def setUp(self):
        super().setUp()
        self.controller = lock_server.LockServerController()
        self.compute_api = self.controller.compute_api

    def test_lock_unlock(self):
        args_map = {'_lock': ((), {"reason": None})}
        body_map = {'_lock': {'lock': None}, '_unlock': {'unlock': None}}
        self._test_actions(['_lock', '_unlock'], args_map=args_map,
            body_map=body_map)

    def test_lock_unlock_with_non_existed_instance(self):
        body_map = {'_lock': {'lock': None}, '_unlock': {'unlock': None}}
        self._test_actions_with_non_existed_instance(['_lock', '_unlock'],
            body_map=body_map)

    @mock.patch.object(common, 'get_instance')
    def test_unlock_with_any_body(self, get_instance_mock):
        instance = fake_instance.fake_instance_obj(
            self.req.environ['nova.context'])
        get_instance_mock.return_value = instance
        # This will pass since there is no schema validation.
        body = {'unlock': {'blah': 'blah'}}

        with mock.patch.object(self.compute_api, 'unlock') as mock_lock:
            self.controller._unlock(self.req, instance.uuid, body=body)
            mock_lock.assert_called_once_with(
                self.req.environ['nova.context'], instance)

    @mock.patch.object(common, 'get_instance')
    def test_lock_with_empty_dict_body_is_valid(self, get_instance_mock):
        # Empty dict with no key in the body is allowed.
        instance = fake_instance.fake_instance_obj(
            self.req.environ['nova.context'])
        get_instance_mock.return_value = instance
        body = {'lock': {}}

        with mock.patch.object(self.compute_api, 'lock') as mock_lock:
            self.controller._lock(self.req, instance.uuid, body=body)
            mock_lock.assert_called_once_with(
                self.req.environ['nova.context'], instance, reason=None)


class LockServerTestsV273(LockServerTests):

    def setUp(self):
        super(LockServerTestsV273, self).setUp()
        self.req.api_version_request = api_version_request.APIVersionRequest(
            '2.73')

    @mock.patch.object(common, 'get_instance')
    def test_lock_with_reason_V273(self, get_instance_mock):
        instance = fake_instance.fake_instance_obj(
            self.req.environ['nova.context'])
        get_instance_mock.return_value = instance
        reason = "I don't want to work"
        body = {'lock': {"locked_reason": reason}}

        with mock.patch.object(self.compute_api, 'lock') as mock_lock:
            self.controller._lock(self.req, instance.uuid, body=body)
            mock_lock.assert_called_once_with(
                self.req.environ['nova.context'], instance, reason=reason)

    def test_lock_with_reason_exceeding_255_chars(self):
        instance = fake_instance.fake_instance_obj(
            self.req.environ['nova.context'])
        reason = 's' * 256
        body = {'lock': {"locked_reason": reason}}

        exp = self.assertRaises(exception.ValidationError,
            self.controller._lock, self.req, instance.uuid, body=body)
        self.assertIn('is too long', str(exp))

    def test_lock_with_reason_in_invalid_format(self):
        instance = fake_instance.fake_instance_obj(
            self.req.environ['nova.context'])
        reason = 256
        body = {'lock': {"locked_reason": reason}}

        exp = self.assertRaises(exception.ValidationError,
            self.controller._lock, self.req, instance.uuid, body=body)
        self.assertIn("256 is not of type 'string'", str(exp))

    def test_lock_with_invalid_parameter(self):
        # This will fail from 2.73 since we have a schema check that allows
        # only locked_reason
        instance = fake_instance.fake_instance_obj(
            self.req.environ['nova.context'])
        body = {'lock': {'blah': 'blah'}}

        exp = self.assertRaises(exception.ValidationError,
            self.controller._lock, self.req, instance.uuid, body=body)
        self.assertIn("('blah' was unexpected)", str(exp))
