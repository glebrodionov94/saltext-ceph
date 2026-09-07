"""Salt-facing composition for public iSCSI Dashboard operations."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import iscsi
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph.errors import ConfigurationError


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def _password(source):
    if source is None:
        return ""
    value = secret_file.read(source).rstrip("\r\n")
    if not value:
        raise ConfigurationError("Password file contains only line separators.")
    return value


def get_discovery_auth(opts, pillar, context, include_secrets=False, profile="default"):
    """Return discovery CHAP configuration, redacting passwords by default."""
    return iscsi.get_discovery_auth(
        _client(opts, pillar, context, profile), include_secrets
    ).as_dict()


def set_discovery_auth(
    opts,
    pillar,
    context,
    user="",
    password_source=None,
    mutual_user="",
    mutual_password_source=None,
    profile="default",
):
    """Set or disable discovery CHAP credentials using local secret files."""
    return iscsi.set_discovery_auth(
        _client(opts, pillar, context, profile),
        user,
        _password(password_source),
        mutual_user,
        _password(mutual_password_source),
    ).as_dict()


def list_targets(opts, pillar, context, include_secrets=False, profile="default"):
    """List iSCSI targets with CHAP passwords redacted by default."""
    return iscsi.list_targets(_client(opts, pillar, context, profile), include_secrets).as_dict()


def get_target(opts, pillar, context, target_iqn, include_secrets=False, profile="default"):
    """Return one iSCSI target with CHAP passwords redacted by default."""
    return iscsi.get_target(
        _client(opts, pillar, context, profile), target_iqn, include_secrets
    ).as_dict()


def create_target(
    opts,
    pillar,
    context,
    target_iqn,
    portals,
    target_controls=None,
    acl_enabled=False,
    auth=None,
    disks=None,
    clients=None,
    groups=None,
    profile="default",
):
    """Create an iSCSI target."""
    return iscsi.create_target(
        _client(opts, pillar, context, profile),
        target_iqn,
        portals,
        target_controls,
        acl_enabled,
        auth,
        disks,
        clients,
        groups,
    ).as_dict()


def update_target(
    opts,
    pillar,
    context,
    target_iqn,
    portals,
    new_target_iqn=None,
    target_controls=None,
    acl_enabled=False,
    auth=None,
    disks=None,
    clients=None,
    groups=None,
    confirm=False,
    profile="default",
):
    """Replace an iSCSI target after confirmation."""
    return iscsi.update_target(
        _client(opts, pillar, context, profile),
        target_iqn,
        portals,
        new_target_iqn,
        target_controls,
        acl_enabled,
        auth,
        disks,
        clients,
        groups,
        confirm,
    ).as_dict()


def delete_target(
    opts,
    pillar,
    context,
    target_iqn,
    confirm=False,
    profile="default",
):
    """Delete an iSCSI target after confirmation."""
    return iscsi.delete_target(
        _client(opts, pillar, context, profile), target_iqn, confirm
    ).as_dict()
