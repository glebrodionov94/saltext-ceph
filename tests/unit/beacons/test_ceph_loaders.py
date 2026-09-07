"""Salt loader discovery for the Ceph beacon plugins."""

import salt.loader

import saltext.ceph


def test_salt_loader_discovers_beacons_and_their_validators(minion_opts, monkeypatch):
    beacon_dir = saltext.ceph.PACKAGE_ROOT / "beacons"
    monkeypatch.setattr(salt.loader, "_module_dirs", lambda *_args: [str(beacon_dir)])
    loaded = salt.loader.beacons(minion_opts, {}, context={})
    expected = {
        "ceph_certificate.beacon",
        "ceph_certificate.validate",
        "ceph_health.beacon",
        "ceph_health.validate",
        "ceph_task.beacon",
        "ceph_task.validate",
    }
    assert expected.issubset(loaded)
    assert loaded["ceph_health.validate"]([]) == (True, "Valid beacon configuration.")
