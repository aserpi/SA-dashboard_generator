import html
import json
import re

import lxml.etree  # Splunk-provided package

import import_declare_test  # Always put this line before third-party imports
from solnlib.acl import ACLManager
from solnlib.modular_input.checkpointer import KVStoreCheckpointer
from solnlib.splunk_rest_client import SplunkRestClient
from solnlib.utils import is_true
from splunklib.binding import HTTPError

from _templates import _permissions_template, _scheduled_view_template


def _delete_dashboards(helper, client, checkpoint, del_prev, del_regex):
    dashboard_ids = set()
    if del_prev and helper.search_name:
        prev_checkpoint = checkpoint.get(helper.search_name)
        if prev_checkpoint:
            dashboard_ids = set(prev_checkpoint["dashboard_ids"])
    dashboards_regex = re.compile(del_regex) if del_regex else None

    dashboards_res = client.get(f"data/ui/views", count=-1, output_mode="json").body.read()
    for dashboard in json.loads(dashboards_res)["entry"]:
        title = dashboard["name"]
        if (dashboard["acl"]["app"] == client.namespace.app
                and (title in dashboard_ids
                     or (dashboards_regex and dashboards_regex.search(title)))):
            client.delete(f"data/ui/views/{title}")
            helper.log_info(f"Deleted dashboard '{title}'.")

    scheduled_view_res = client.get(f"scheduled/views", count=-1, output_mode="json").body.read()
    for scheduled_view in json.loads(scheduled_view_res)["entry"]:
        pdf_view = scheduled_view["content"]["action.email.pdfview"]
        if (scheduled_view["acl"]["app"] == client.namespace.app
                and (pdf_view in dashboard_ids
                     or (dashboards_regex and dashboards_regex.search(pdf_view)))):
            client.delete(f"scheduled/views/{scheduled_view['name']}")
            helper.log_info(f"Deleted scheduled view '{scheduled_view['name']}'.")


def _dashboard_studio_def(pattern, event, template_dashboard_def):
    json_escaped_repls = {re.escape(fr"__{k}__"): v.replace('"', r'\"')
                          for k, v in event.items() if not k.startswith("__mv_") and v is not None}
    repls = {re.escape(fr"__{k}__"): v
             for k, v in event.items() if not k.startswith("__mv_") and v is not None}
    root = lxml.etree.fromstring(template_dashboard_def)
    for child in root:
        if child.tag in ["definition", "meta"]:
            child.text = lxml.etree.CDATA(_multiple_replace(pattern, json_escaped_repls,
                                                            child.text))
        elif child.text:
            child.text = _multiple_replace(pattern, repls, child.text)
    return lxml.etree.tostring(root, encoding="unicode")


def _generate_dashboard(helper, client, dashboard_id, dashboard_def, dashboard_url):
    created = False
    try:
        client.post("data/ui/views", **{"eai:data": dashboard_def, "name": dashboard_id})
        created = True
        helper.log_info(f"Created dashboard '{dashboard_id}'.")
    except HTTPError as e:
        if e.status == 409:  # Dashboard already exists
            try:
                client.post(dashboard_url, **{"eai:data": dashboard_def})
                created = True
            except Exception:
                helper.log_error(f"Error when creating dashboard '{dashboard_id}'.")
        else:
            helper.log_error(f"Error when creating dashboard '{dashboard_id}'.")
    except Exception:
        helper.log_error(f"Error when creating dashboard '{dashboard_id}'.")
    finally:
        return created


def _get_param(helper, param, label=None):
    label = label if label else f"'{param}'"
    param_value = helper.get_param(param)
    if param_value is None:
        helper.log_debug(f"Found no {label}.")
    else:
        helper.log_debug(f"Found {label} '{param_value}'.")
    return param_value


def _multiple_replace(pattern, repls, item):
    if isinstance(item, list):
        return [_multiple_replace(pattern, repls, s) for s in item]
    return pattern.sub(lambda m: repls[re.escape(m.group(0))], item)


def process_event(helper, *args, **kwargs):
    helper.log_info("Alert action generate_dashboards started.")

    del_prev = is_true(_get_param(helper, "del_prev"))
    del_regex = _get_param(helper, "del_regex")
    dest_app = _get_param(helper, "dest_app")
    permissions_template = _get_param(helper, "permissions_template")
    template_dashboard_id = _get_param(helper, "template_dashboard_id")
    scheduled_view_template = _get_param(helper, "scheduled_view_template")
    src_app = _get_param(helper, "src_app")

    dest_app = dest_app if dest_app else src_app
    acl_manager = ACLManager(helper.session_key, dest_app) if permissions_template else None
    dest_client = SplunkRestClient(helper.session_key, dest_app)
    src_client = SplunkRestClient(helper.session_key, src_app)

    template_dashboard_res = json.loads(
        src_client.get(f"data/ui/views/{template_dashboard_id}", count=1, output_mode="json")
                  .body
                  .read()
    )["entry"][0]["content"]
    template_dashboard_def = template_dashboard_res["eai:data"]
    template_dashboard_version = template_dashboard_res["version"]
    template_permissions_params = (_permissions_template(helper, permissions_template)
                                   if permissions_template else None)
    template_scheduled_view_params = (_scheduled_view_template(helper, scheduled_view_template)
                                      if scheduled_view_template else None)

    checkpoint = KVStoreCheckpointer(helper.action_name, helper.session_key, helper.ta_name)
    if del_prev or del_regex:
        _delete_dashboards(helper, dest_client, checkpoint, del_prev, del_regex)

    try:
        events = helper.get_events()
    except SystemExit:
        events = []

    dashboard_ids = []
    for event in events:
        if template_dashboard_version == "2":
            repls = {re.escape(fr"__{k}__"): v
                     for k, v in event.items() if not k.startswith("__mv_") and v is not None}
            pattern = re.compile("|".join(repls))

            dashboard_def = _dashboard_studio_def(pattern, event, template_dashboard_def)
        else:
            escaped_repls = {re.escape(fr"__{k}__"): html.escape(v)
                             for k, v in event.items() if not k.startswith("__mv_") and v is not None}
            repls = {re.escape(fr"__{k}__"): json.dumps(v)
                     for k, v in event.items() if not k.startswith("__mv_") and v is not None}
            pattern = re.compile("|".join(repls))
            dashboard_def = _multiple_replace(pattern, escaped_repls, template_dashboard_def)

        dashboard_id = _multiple_replace(pattern, repls, template_dashboard_id)
        dashboard_url = f"data/ui/views/{dashboard_id}"
        if not _generate_dashboard(helper, dest_client, dashboard_id, dashboard_def,
                                   dashboard_url):
            continue
        dashboard_ids.append(dashboard_id)

        permissions_params = {}
        if acl_manager:
            permissions_params = {k: _multiple_replace(pattern, repls, v)
                                  for k, v in template_permissions_params.items()}
            try:
                acl_manager.update(f"{dashboard_url}/acl", **permissions_params)
            except Exception:
                helper.log_error("Error when changing permissions of dashboard "
                                 f"'{dashboard_id}'.")

        if template_scheduled_view_params:
            scheduled_view_id = f"_ScheduledView__{dashboard_id}"
            scheduled_view_params = {k: _multiple_replace(pattern, repls, v)
                                     for k, v in template_scheduled_view_params.items()}
            scheduled_view_params["is_scheduled"] = True
            scheduled_view_url = f"scheduled/views/{scheduled_view_id}"
            try:
                dest_client.post(scheduled_view_url, **scheduled_view_params)
                helper.log_info(f"Created scheduled view '{scheduled_view_id}'.")
            except Exception:
                helper.log_error(f"Error when creating scheduled view '{scheduled_view_id}'.")
                continue

            if acl_manager:
                try:
                    acl_manager.update(f"{scheduled_view_url}/acl", **permissions_params)
                except Exception:
                    helper.log_error(f"Error when changing permissions of scheduled view "
                                     f"'{scheduled_view_id}'.")

    if helper.search_name:
        checkpoint.update(helper.search_name, {"dashboard_ids": dashboard_ids})

    helper.log_info("Alert action generate_dashboards ended.")
    return 0
