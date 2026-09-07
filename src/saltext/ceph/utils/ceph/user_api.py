"""Salt-facing composition for CephX users and secret keyring files."""

from saltext.ceph.utils import ceph
from saltext.ceph.utils.ceph import secret_file
from saltext.ceph.utils.ceph import users


def _client(opts, pillar, context, profile):
    return ceph.get_client(opts, pillar, context, profile)


def list_(opts, pillar, context, profile="default"):
    """List CephX entities and masked capabilities."""
    return users.list_(_client(opts, pillar, context, profile)).as_dict()


def get(opts, pillar, context, user_entity, profile="default"):
    """Return one CephX entity, or ``None`` when it is absent."""
    return users.get(_client(opts, pillar, context, profile), user_entity).as_dict()


def create(opts, pillar, context, user_entity, capabilities, profile="default"):
    """Create one CephX entity."""
    return users.create(
        _client(opts, pillar, context, profile), user_entity, capabilities
    ).as_dict()


def update(opts, pillar, context, user_entity, capabilities, profile="default"):
    """Replace an entity's complete capability set."""
    return users.update(
        _client(opts, pillar, context, profile), user_entity, capabilities
    ).as_dict()


def delete(opts, pillar, context, user_entity, confirm=False, profile="default"):
    """Delete one CephX entity after explicit confirmation."""
    return users.delete(_client(opts, pillar, context, profile), user_entity, confirm).as_dict()


def import_keyring(opts, pillar, context, source, profile="default"):
    """Import keyring contents from a local file without returning the secret."""
    keyring = secret_file.read(source)
    response = users.import_keyring(_client(opts, pillar, context, profile), keyring)
    return {
        "status": response.status,
        "data": {"source": str(source)},
        "headers": response.headers,
    }


def export_keyring(
    opts, pillar, context, entities, destination, overwrite=False, profile="default"
):
    """Export keyrings to a local 0600 file and return only safe metadata."""
    normalized = users.validate_entities(entities)
    response = users.export_keyring(_client(opts, pillar, context, profile), normalized)
    path = secret_file.write(destination, response.data, overwrite=overwrite)
    return {
        "status": response.status,
        "data": {"entities": normalized, "destination": path},
        "headers": response.headers,
    }
