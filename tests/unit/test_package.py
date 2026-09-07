"""Verify the installed distribution can be discovered by Salt."""

from importlib import metadata

import saltext.ceph


def test_salt_loader_entry_point():
    """Package installation must register the extension with Salt's loader."""
    distribution = metadata.distribution("saltext.ceph")
    entry_points = [entry for entry in distribution.entry_points if entry.group == "salt.loader"]

    assert len(entry_points) == 1
    assert entry_points[0].name == "saltext.ceph"
    assert entry_points[0].load() is saltext.ceph


def test_installed_package_layout():
    """Loader directories and version metadata must survive packaging."""
    distribution = metadata.distribution("saltext.ceph")

    assert saltext.ceph.__version__ == distribution.version
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "__init__.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "states" / "__init__.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "ceph.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "ceph_auth.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "client.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "ceph_auth.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "ceph_users.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "ceph_users.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "cephfs.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "cephfs.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "cephfs.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "cephfs_api.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "cephfs_mirror.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "cephfs_schedule.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "cephfs_volumes.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "local_file.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "ceph_certificates.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "ceph_certificates.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "certificates.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "certificate_api.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "ceph_cluster.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "ceph_cluster.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "cluster.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "cluster_api.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "ceph_cluster_config.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "ceph_cluster_config.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "cluster_configuration.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "cluster_configuration_api.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "ceph_crush_rule.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "ceph_crush_rule.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "crush_rule.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "crush_rule_api.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "ceph_daemon.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "ceph_daemon.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "daemon.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "daemon_api.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "ceph_erasure_code_profile.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "ceph_erasure_code_profile.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "erasure_code_profile.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "erasure_code_profile_api.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "modules" / "ceph_grafana.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "wrapper" / "ceph_grafana.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "grafana.py").is_file()
    assert (saltext.ceph.PACKAGE_ROOT / "utils" / "ceph" / "grafana_api.py").is_file()
