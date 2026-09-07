"""Operations from Dashboard's public ``hardware.py`` controller."""

from saltext.ceph.utils.ceph import validation

API_VERSION = "0.1"
RESOURCE_PATH = "/api/hardware/summary"
CATEGORIES = frozenset(
    ("memory", "storage", "processors", "network", "power", "fans", "temperatures")
)


def summary(client, categories=None, hostnames=None):
    """Return orchestrator hardware health totals, optionally filtered."""
    categories = validation.string_list(categories, "categories", allowed=CATEGORIES, optional=True)
    hostnames = validation.string_list(hostnames, "hostnames", optional=True)
    params = {}
    if categories is not None:
        params["categories"] = categories
    if hostnames is not None:
        params["hostname"] = hostnames
    response = client.request("GET", RESOURCE_PATH, api_version=API_VERSION, params=params)
    return validation.mapping_response(response, "Ceph hardware summary")
