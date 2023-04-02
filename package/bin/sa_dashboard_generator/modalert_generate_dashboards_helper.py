import json
import re

import import_declare_test  # Always put this line before third-party imports
from solnlib.modular_input.checkpointer import KVStoreCheckpointer
from solnlib.splunk_rest_client import SplunkRestClient
from solnlib.utils import is_true
from splunklib.binding import HTTPError


def _delete_dashboards(helper, client, dashboard_ids, dashboards_regex=None):
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
    template_dashboard_id = _get_param(helper, "template_dashboard_id")
    src_app = _get_param(helper, "src_app")

    dest_app = dest_app if dest_app else src_app
    dest_client = SplunkRestClient(helper.session_key, dest_app)
    src_client = SplunkRestClient(helper.session_key, src_app)

    template_dashboard_res = src_client.get(f"data/ui/views/{template_dashboard_id}", count=1,
                                            output_mode="json").body.read()
    template_dashboard_def = json.loads(template_dashboard_res)["entry"][0]["content"]["eai:data"]

    checkpoint = KVStoreCheckpointer(helper.action_name, helper.session_key, helper.ta_name)
    prev_dashboard_ids = set()
    if del_prev and helper.search_name:
        prev_checkpoint = checkpoint.get(helper.search_name)
        if prev_checkpoint:
            prev_dashboard_ids = set(prev_checkpoint["dashboard_ids"])
    del_regex_compiled = re.compile(del_regex) if del_regex else None
    _delete_dashboards(helper, dest_client, prev_dashboard_ids, del_regex_compiled)

    dashboard_ids = []
    for event in helper.get_events():
        repls = {re.escape(fr"__{k}__"): v
                 for k, v in event.items() if not k.startswith("__mv_") and v is not None}
        pattern = re.compile("|".join(repls))
        dashboard_def = _multiple_replace(pattern, repls, template_dashboard_def)
        dashboard_id = _multiple_replace(pattern, repls, template_dashboard_id)
        dashboard_url = f"data/ui/views/{dashboard_id}"

        try:
            dest_client.post("data/ui/views", **{"eai:data": dashboard_def, "name": dashboard_id})
        except HTTPError as e:
            if e.status == 409:  # Dashboard already exists
                dest_client.post(dashboard_url, **{"eai:data": dashboard_def})
            else:
                helper.log_error(f"Error when creating dashboard '{dashboard_id}'.")
                continue
        except Exception:
            helper.log_error(f"Error when creating dashboard '{dashboard_id}'.")
            continue

        dashboard_ids.append(dashboard_id)
        helper.log_info(f"Created dashboard '{dashboard_id}'.")

    if helper.search_name:
        checkpoint.update(helper.search_name, {"dashboard_ids": dashboard_ids})

    helper.log_info("Alert action generate_dashboards ended.")
    return 0
