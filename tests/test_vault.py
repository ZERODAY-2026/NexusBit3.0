import gc
import os

from lexlocal.privacy import vault as vault_mod
from lexlocal.privacy.vault import Vault


def test_items_are_encrypted_at_rest_and_round_trip():
    v = Vault()
    secret = b"The Tenant shall pay a monthly rent of Rs. 25,000"
    v.put("page-1", secret)
    on_disk = open(v.files()[0], "rb").read()
    assert secret not in on_disk and b"25,000" not in on_disk
    assert v.get("page-1") == secret
    v.wipe()


def test_wipe_removes_files_dir_and_key():
    v = Vault()
    v.put("x", b"data")
    open(os.path.join(v.scratch_dir(), "img.png"), "wb").write(b"plain image bytes")
    d = v.dir
    assert v.wipe() == 2
    assert not os.path.exists(d) and not v.active and v.get("x") is None


def test_another_vaults_key_cannot_decrypt():
    a, b = Vault(), Vault()
    a.put("x", b"secret")
    os.replace(a.files()[0], os.path.join(b.dir, "x.bin"))
    assert b.get("x") is None
    a.wipe(); b.wipe()


def test_garbage_collected_session_wipes_its_vault():
    v = Vault()
    v.put("x", b"data")
    d = v.dir
    del v
    gc.collect()
    assert not os.path.exists(d)


def test_panic_wipe_all():
    vs = [Vault() for _ in range(3)]
    for v in vs:
        v.put("x", b"data")
    assert vault_mod.wipe_all() >= 3
    assert all(not os.path.exists(v.dir) for v in vs)
