"""Public Dashboard RGW daemon and site controller operations."""

from saltext.ceph.utils.ceph import rgw_common as common
from saltext.ceph.utils.ceph.errors import ConfigurationError

API_VERSION = "1.0"
DAEMON_PATH = "/api/rgw/daemon"
SITE_PATH = "/api/rgw/site"
_SITE_QUERIES = frozenset(("placement-targets", "realms", "default-realm", "default-zonegroup"))


def list_daemons(client):
    """List RGW daemons."""
    result = client.request("GET", DAEMON_PATH, api_version=API_VERSION)
    return common.safe_response(result, "RGW daemon list", shape="mapping_list")


def get_daemon(client, service_id):
    """Return metadata and status for one RGW daemon."""
    result = client.request(
        "GET", f"{DAEMON_PATH}/{common.segment(service_id, 'service_id')}", api_version=API_VERSION
    )
    return common.safe_response(result, "RGW daemon", shape="mapping")


def set_multisite_config(
    client, realm_name=None, zonegroup_name=None, zone_name=None, daemon_name=None
):
    """Select the realm, zonegroup, zone, and daemon used by Dashboard."""
    data = common.params(
        realm_name=common.optional_text(realm_name, "realm_name"),
        zonegroup_name=common.optional_text(zonegroup_name, "zonegroup_name"),
        zone_name=common.optional_text(zone_name, "zone_name"),
        daemon_name=common.optional_text(daemon_name, "daemon_name"),
    )
    result = client.request(
        "PUT", f"{DAEMON_PATH}/set_multisite_config", api_version=API_VERSION, data=data
    )
    return common.response_copy(result, "RGW multisite configuration")


def get_site(client, query, daemon_name=None):
    """Read one of the four implemented RGW site queries."""
    query = common.name(query, "query")
    if query not in _SITE_QUERIES:
        raise ConfigurationError("query is not implemented by the public RGW site controller.")
    request_params = common.params(
        query=query,
        daemon_name=common.optional_text(daemon_name, "daemon_name"),
    )
    result = client.request("GET", SITE_PATH, api_version=API_VERSION, params=request_params)
    return common.safe_response(result, "RGW site query")
