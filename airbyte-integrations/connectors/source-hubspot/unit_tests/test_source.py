#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#


import logging
from functools import partial

import pytest
from airbyte_cdk.sources.deprecated.base_source import ConfiguredAirbyteCatalog, Type
from source_hubspot.api import (
    API,
    PROPERTIES_PARAM_MAX_LENGTH,
    CRMObjectIncrementalStream,
    CRMSearchStream,
    Deals,
    Workflows,
    split_properties,
)
from source_hubspot.source import SourceHubspot

NUMBER_OF_PROPERTIES = 2000

logger = logging.getLogger("test_client")


@pytest.fixture(name="oauth_config")
def oauth_config_fixture():
    return {
        "start_date": "2021-10-10T00:00:00Z",
        "credentials": {
            "credentials_title": "OAuth Credentials",
            "redirect_uri": "https://airbyte.io",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "refresh_token": "test_refresh_token",
            "access_token": "test_access_token",
            "token_expires": "2021-05-30T06:00:00Z",
        },
    }


@pytest.fixture(name="common_params")
def common_params_fixture(config):
    source = SourceHubspot()
    common_params = source.get_common_params(config=config)
    return common_params


@pytest.fixture(name="config")
def config_fixture():
    return {"start_date": "2021-01-10T00:00:00Z", "credentials": {"credentials_title": "API Key Credentials", "api_key": "test_api_key"}}


@pytest.fixture(name="some_credentials")
def some_credentials_fixture():
    return {"credentials_title": "API Key Credentials", "api_key": "wrong_key"}


@pytest.fixture(name="creds_with_wrong_permissions")
def creds_with_wrong_permissions():
    return {"credentials_title": "API Key Credentials", "api_key": "THIS-IS-THE-API_KEY"}


@pytest.fixture(name="fake_properties_list")
def fake_properties_list():
    return [f"property_number_{i}" for i in range(NUMBER_OF_PROPERTIES)]


def test_check_connection_backoff_on_limit_reached(requests_mock, config):
    """Error once, check that we retry and not fail"""
    responses = [
        {"json": {"error": "limit reached"}, "status_code": 429, "headers": {"Retry-After": "0"}},
        {"json": [], "status_code": 200},
    ]

    requests_mock.register_uri("GET", "/properties/v2/contact/properties", responses)
    source = SourceHubspot()
    alive, error = source.check_connection(logger=logger, config=config)

    assert alive
    assert not error


def test_check_connection_backoff_on_server_error(requests_mock, config):
    """Error once, check that we retry and not fail"""
    responses = [
        {"json": {"error": "something bad"}, "status_code": 500},
        {"json": [], "status_code": 200},
    ]
    requests_mock.register_uri("GET", "/properties/v2/contact/properties", responses)
    source = SourceHubspot()
    alive, error = source.check_connection(logger=logger, config=config)

    assert alive
    assert not error


def test_wrong_permissions_api_key(requests_mock, creds_with_wrong_permissions, common_params):
    """
    Error with API Key Permissions to particular stream,
    typically this issue raises along with calling `workflows` stream with API Key
    that doesn't have required permissions to read the stream.
    """

    # Mapping tipical response for mocker
    responses = [
        {
            "json": {
                "status": "error",
                "message": f'This hapikey ({creds_with_wrong_permissions.get("api_key")}) does not have proper permissions! (requires any of [automation-access])',
                "correlationId": "2fe0a9af-3609-45c9-a4d7-83a1774121aa",
            }
        }
    ]

    # We expect something like this
    expected_warining_message = {
        "type": "LOG",
        "log": {
            "level": "WARN",
            "message": f'Stream `workflows` cannot be procced. This hapikey ({creds_with_wrong_permissions.get("api_key")}) does not have proper permissions! (requires any of [automation-access])',
        },
    }

    api = API(creds_with_wrong_permissions)

    # Create test_stream instance
    test_stream = Workflows(**common_params)

    # Mocking Request
    requests_mock.register_uri("GET", test_stream.url, responses)

    # Mock the getter method that handles requests.
    def get(url=test_stream.url, params=None):
        response = api._session.get(api.BASE_URL + url, params=params)
        return api._parse_and_handle_errors(response)

    # Define request params value
    params = {"limit": 100, "properties": ""}

    # Read preudo-output from generator object _read(), based on real scenario
    list(test_stream._read(getter=get, params=params))

    # match logged expected logged warning message with output given from preudo-output
    assert expected_warining_message


class TestSplittingPropertiesFunctionality:
    BASE_OBJECT_BODY = {
        "createdAt": "2020-12-10T07:58:09.554Z",
        "updatedAt": "2021-07-31T08:18:58.954Z",
        "archived": False,
    }

    @pytest.fixture
    def api(self, some_credentials):
        return API(some_credentials)

    @staticmethod
    def set_mock_properties(requests_mock, url, fake_properties_list):
        properties_response = [
            {
                "json": [
                    {"name": property_name, "type": "string", "updatedAt": 1571085954360, "createdAt": 1565059306048}
                    for property_name in fake_properties_list
                ],
                "status_code": 200,
            },
        ]
        requests_mock.register_uri("GET", url, properties_response)

    # Mock the getter method that handles requests.
    def get(self, url, api, params=None):
        response = api._session.get(api.BASE_URL + url, params=params)
        return api._parse_and_handle_errors(response)

    def test_splitting_properties(self, fake_properties_list):
        """
        Check that properties are split into multiple arrays
        """
        for slice_property in split_properties(fake_properties_list):
            slice_length = [len(item) for item in slice_property]
            assert sum(slice_length) <= PROPERTIES_PARAM_MAX_LENGTH

    def test_stream_with_splitting_properties(self, requests_mock, api, fake_properties_list, common_params):
        """
        Check working stream `companies` with large list of properties using new functionality with splitting properties
        """
        test_stream = CRMSearchStream(
            entity="company", last_modified_field="hs_lastmodifieddate", associations=["contacts"], name="companies", **common_params
        )
        parsed_properties = list(split_properties(fake_properties_list))
        self.set_mock_properties(requests_mock, "/properties/v2/company/properties", fake_properties_list)

        record_ids_paginated = [list(map(str, range(100))), list(map(str, range(100, 150, 1)))]

        after_id = None
        for id_list in record_ids_paginated:
            for property_slice in parsed_properties:
                record_responses = [
                    {
                        "json": {
                            "results": [
                                {**self.BASE_OBJECT_BODY, **{"id": id, "properties": {p: "fake_data" for p in property_slice}}}
                                for id in id_list
                            ],
                            "paging": {"next": {"after": id_list[-1]}} if len(id_list) == 100 else {},
                        },
                        "status_code": 200,
                    }
                ]
                requests_mock.register_uri(
                    "GET",
                    f"{test_stream.url}?limit=100&properties={','.join(property_slice)}{f'&after={after_id}' if after_id else ''}",
                    record_responses,
                )
            after_id = id_list[-1]

        # Read preudo-output from generator object read(), based on real scenario
        stream_records = list(test_stream.read(getter=partial(self.get, test_stream.url, api=api)))

        # check that we have records for all set ids, and that each record has 2000 properties (not more, and not less)
        assert len(stream_records) == sum([len(ids) for ids in record_ids_paginated])
        for record in stream_records:
            assert len(record["properties"]) == NUMBER_OF_PROPERTIES

    def test_stream_with_splitting_properties_with_pagination(self, requests_mock, common_params, api, fake_properties_list):
        """
        Check working stream `products` with large list of properties using new functionality with splitting properties
        """

        parsed_properties = list(split_properties(fake_properties_list))
        self.set_mock_properties(requests_mock, "/properties/v2/product/properties", fake_properties_list)

        test_stream = CRMObjectIncrementalStream(entity="product", name="products", **common_params)
        for property_slice in parsed_properties:
            record_responses = [
                {
                    "json": {
                        "results": [
                            {**self.BASE_OBJECT_BODY, **{"id": id, "properties": {p: "fake_data" for p in property_slice}}}
                            for id in ["6043593519", "1092593519", "1092593518", "1092593517", "1092593516"]
                        ],
                        "paging": {},
                    },
                    "status_code": 200,
                }
            ]
            requests_mock.register_uri("GET", f"{test_stream.url}?properties={','.join(property_slice)}", record_responses)

        stream_records = list(test_stream.read(getter=partial(self.get, test_stream.url, api=api)))

        assert len(stream_records) == 5
        for record in stream_records:
            assert len(record["properties"]) == NUMBER_OF_PROPERTIES

    def test_stream_with_splitting_properties_with_new_record(self, requests_mock, common_params, api, fake_properties_list):
        """
        Check working stream `workflows` with large list of properties using new functionality with splitting properties
        """

        parsed_properties = list(split_properties(fake_properties_list))
        self.set_mock_properties(requests_mock, "/properties/v2/deal/properties", fake_properties_list)

        test_stream = Deals(associations=["contacts"], **common_params)

        ids_list = ["6043593519", "1092593519", "1092593518", "1092593517", "1092593516"]
        for property_slice in parsed_properties:
            record_responses = [
                {
                    "json": {
                        "results": [
                            {**self.BASE_OBJECT_BODY, **{"id": id, "properties": {p: "fake_data" for p in property_slice}}}
                            for id in ids_list
                        ],
                        "paging": {},
                    },
                    "status_code": 200,
                }
            ]
            requests_mock.register_uri("GET", f"{test_stream.url}?properties={','.join(property_slice)}", record_responses)
            ids_list.append("1092593513")

        stream_records = list(test_stream.read(getter=partial(self.get, test_stream.url, api=api)))

        assert len(stream_records) == 6


@pytest.fixture(name="configured_catalog")
def configured_catalog_fixture():
    configured_catalog = {
        "streams": [
            {
                "stream": {
                    "name": "quotes",
                    "json_schema": {},
                    "supported_sync_modes": ["full_refresh", "incremental"],
                    "source_defined_cursor": True,
                    "default_cursor_field": ["updatedAt"],
                },
                "sync_mode": "incremental",
                "cursor_field": ["updatedAt"],
                "destination_sync_mode": "append",
            }
        ]
    }
    return ConfiguredAirbyteCatalog.parse_obj(configured_catalog)


def test_it_should_not_read_quotes_stream_if_it_does_not_exist_in_client(oauth_config, configured_catalog):
    """
    If 'quotes' stream is not in the client, it should skip it.
    """
    source = SourceHubspot()

    all_records = list(source.read(logger, config=oauth_config, catalog=configured_catalog, state=None))
    records = [record for record in all_records if record.type == Type.RECORD]
    assert not records
