import json
import logging

import pytest
import requests
import responses
from requests.exceptions import ConnectionError

from jbi.environment import get_settings
from jbi.services import jira


@pytest.mark.no_mocked_jira
def test_jira_create_issue_is_instrumented(
    mocked_responses, context_create_example, mocked_statsd
):
    url = f"{get_settings().jira_base_url}rest/api/2/project/{context_create_example.jira.project}/components"
    mocked_responses.add(
        responses.GET,
        url,
        json=[
            {
                "id": "10000",
                "name": "Component 1",
            },
            {
                "id": "42",
                "name": "Remote Settings",
            },
        ],
    )

    url = f"{get_settings().jira_base_url}rest/api/2/issue"
    mocked_responses.add(
        responses.POST,
        url,
        json={
            "id": "10000",
            "key": "ED-24",
        },
    )

    jira.create_jira_issue(
        context_create_example,
        "Description",
        sync_whiteboard_labels=False,
        components=["Remote Settings"],
    )
    jira_client = jira.get_client()

    jira_client.create_issue({})

    mocked_statsd.incr.assert_called_with("jbi.jira.methods.create_issue.count")
    mocked_statsd.timer.assert_called_with("jbi.jira.methods.create_issue.timer")


@pytest.mark.no_mocked_jira
def test_jira_calls_log_http_errors(mocked_responses, context_create_example, caplog):
    url = f"{get_settings().jira_base_url}rest/api/2/project/{context_create_example.jira.project}/components"
    mocked_responses.add(
        responses.GET,
        url,
        status=404,
        json={
            "errorMessages": ["No project could be found with key 'X'."],
            "errors": {},
        },
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(requests.HTTPError):
            jira.create_jira_issue(
                context_create_example,
                "Description",
                sync_whiteboard_labels=False,
                components=["Remote Settings"],
            )

    log_messages = [log.msg % log.args for log in caplog.records]
    idx = log_messages.index(
        "HTTP: GET /rest/api/2/project/JBI/components -> 404 Not Found"
    )
    log_record = caplog.records[idx]
    assert (
        log_record.body
        == '{"errorMessages": ["No project could be found with key \'X\'."], "errors": {}}'
    )


@pytest.mark.no_mocked_jira
def test_create_issue_with_components(mocked_responses, context_create_example):
    url = f"{get_settings().jira_base_url}rest/api/2/project/{context_create_example.jira.project}/components"
    mocked_responses.add(
        responses.GET,
        url,
        json=[
            {
                "id": "10000",
                "name": "Component 1",
            },
            {
                "id": "42",
                "name": "Remote Settings",
            },
        ],
    )

    url = f"{get_settings().jira_base_url}rest/api/2/issue"
    mocked_responses.add(
        responses.POST,
        url,
        json={
            "id": "10000",
            "key": "ED-24",
        },
    )

    jira.create_jira_issue(
        context_create_example,
        "Description",
        sync_whiteboard_labels=False,
        components=["Remote Settings"],
    )

    posted_data = json.loads(mocked_responses.calls[-1].request.body)

    assert posted_data["fields"]["components"] == [{"id": "42"}]


@pytest.mark.no_mocked_jira
def test_jira_retries_failing_connections_in_health_check(
    mocked_responses, actions_example
):
    url = f"{get_settings().jira_base_url}rest/api/2/serverInfo?doHealthCheck=True"

    # When the request does not match any mocked URL, we also obtain
    # a `ConnectionError`, but let's mock it explicitly.
    mocked_responses.add(
        responses.GET,
        url,
        body=ConnectionError(),
    )

    with pytest.raises(ConnectionError):
        jira.check_health(actions_example)

    assert len(mocked_responses.calls) == 4
