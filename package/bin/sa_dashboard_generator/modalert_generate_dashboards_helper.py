import json
import re

import import_declare_test  # Always put this line before third-party imports
from solnlib.splunk_rest_client import SplunkRestClient
from splunklib.binding import HTTPError


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

    dest_app = _get_param(helper, "dest_app")
    template_dashboard_id = _get_param(helper, "template_dashboard_id")
    src_app = _get_param(helper, "src_app")

    dest_app = dest_app if dest_app else src_app
    dest_client = SplunkRestClient(helper.session_key, dest_app)
    src_client = SplunkRestClient(helper.session_key, src_app)

    template_dashboard_res = src_client.get(f"data/ui/views/{template_dashboard_id}", count=1,
                                            output_mode="json").body.read()
    template_dashboard_def = json.loads(template_dashboard_res)["entry"][0]["content"]["eai:data"]

    for event in helper.get_events():
        repls = {re.escape(fr"__{k}__"): v
                 for k, v in event.items() if not k.startswith("__mv_") and v is not None}
        pattern = re.compile("|".join(repls))
        dashboard_def = _multiple_replace(pattern, repls, template_dashboard_def)
        dashboard_id = _multiple_replace(pattern, repls, template_dashboard_id)
        dashboard_url = f"data/ui/views/{dashboard_id}"

        try:
            dest_client.post("data/ui/views", **{"eai:data": dashboard_def, "name": dashboard_id})
            helper.log_info(f"Created dashboard '{dashboard_id}'.")
        except HTTPError as e:
            if e.status == 409:  # Dashboard already exists
                dest_client.post(dashboard_url, **{"eai:data": dashboard_def})
            else:
                helper.log_error(f"Error when creating dashboard '{dashboard_id}'.")
        except Exception:
            helper.log_error(f"Error when creating dashboard '{dashboard_id}'.")

    helper.log_info("Alert action generate_dashboards ended.")
    return 0
