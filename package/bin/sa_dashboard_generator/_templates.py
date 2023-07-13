import re
import sys

import import_declare_test  # Always put this line before third-party imports
from solnlib.conf_manager import ConfManager, ConfManagerException, ConfStanzaNotExistException


def _permissions_template(helper, template_name):
    conf_manager = ConfManager(helper.session_key, helper.ta_name)
    try:
        templates = conf_manager.get_conf("sa_dashboard_generator_permissions_template")
        template_params = templates.get(template_name)
    except (KeyError, ConfManagerException, ConfStanzaNotExistException):
        helper.log_error("Permissions template not found in configuration file.")
        sys.exit(13)

    owner = template_params.get("owner_")
    perms_read = template_params.get("perms_read")
    perms_write = template_params.get("perms_write")

    perms_read = [perms_read] if isinstance(perms_read, str) else perms_read
    perms_write = [perms_write] if isinstance(perms_write, str) else perms_write
    template_params = {"owner": owner, "perms_read": perms_read, "perms_write": perms_write}
    return {k: v for k, v in template_params.items() if v is not None}


def _scheduled_view_template(helper, template_name):
    conf_manager = ConfManager(helper.session_key, helper.ta_name)
    try:
        templates = conf_manager.get_conf("sa_dashboard_generator_scheduled_view_template")
        template_params = templates.get(template_name)
    except (KeyError, ConfManagerException, ConfStanzaNotExistException):
        helper.log_error("Scheduled view template not found in configuration file.")
        sys.exit(12)

    params = {"action.email.to": template_params["to"],
              "cron_schedule": template_params["cron_schedule"],
              "description": template_params.get("description")}

    for param in re.split(r"(?<!\\)\n", template_params.get("email_params", "")):
        if not param:
            continue
        key, value = param.split("=", 1)
        params[key.strip()] = value.lstrip().replace("\\\n", "\n")

    return params