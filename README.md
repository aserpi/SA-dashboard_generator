# SA-dashboard_generator: Dashboard Generator for Splunk

![GitHub release (latest by date)](https://img.shields.io/github/v/release/aserpi/SA-dashboard_generator)
![Splunk Enterprise](https://img.shields.io/badge/Splunk%20Enterprise-8.0+-67a53e?logo=splunk)
![Splunk Cloud](https://img.shields.io/badge/Splunk%20Cloud-compatible-ed0080?logo=splunk)
![GitHub workflow status](https://img.shields.io/github/actions/workflow/status/aserpi/SA-dashboard_generator/release_action.yml)

This add-on delivers an alert action that generates dashboards (both Simple XML and Dashboard
Studio) from search results and optionally schedules their PDF delivery (Simple XML only).

Starting from a dashboard template, the alert action generates a new dashboard for each result.
If a scheduled view template is selected, PDF deliveries of the dashboards are scheduled.
The add-on can delete dashboards created in the previous run of the saved search (not available for
ad hoc searches) or based on their ID.
When a dashboard is deleted, all associated scheduled views are also deleted.


## String replacement

In templates, all strings in the form `__FIELD__` are replaced with the value of field `FIELD`.
If `FIELD` is null, then the string `__FIELD__` is left untouched.
For example, the two events

| field\_a  | field\_b | field\_c           | field\_d |
|-----------|----------|--------------------|----------|
| "value1a" |          | ""                 | "unused" |
| "value2a" | 1        | "\_\_field\_d\_\_" |          |

encode the string  

```
field_a:__field_a__, field_b:__field_b__, field_c:__field_c__
```

as respectively:

1. `field_a:value1a, field_b:__field_b__, field_c:`
2. `field_a:value2a, field_b:1, field_c:__field_d__`

The ID of the template dashboard should contain string replacements in order to produce a unique ID
per search result.

### Special characters
The add-on automatically escapes HTML and JSON reserved characters (e.g., `&` and `"`) in the
dashboard definition, therefore there is no need to use CDATA in Simple XML dashboards or to
prepend backslashes in Dashboard Studio ones.
Conversely, the creation of valid dashboard IDs (containing only letters, numbers, dashes, and
underscores) is not enforced.


## Templates

The alert action requires an existing dashboard to be used as template and, optionally, a scheduled
view and a permissions template.

Permissions and scheduled view templates can be created in the add-on's configuration page.
In a permissions template, it is possible to specify owner and read and write permissions.
Visibility cannot be changed due to limitations of Splunk libraries.
A scheduled view template allows to specify description, cron schedule, and all `action.email*`
parameters in the same format as `savedsearches.conf`.
