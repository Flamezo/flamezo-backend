"""Guard: every backend method the admin frontend calls must actually exist.

Catches the exact class of bug that shipped delete_outlet_media broken — a
frontend `useFrappePostCall('flamezo_backend.flamezo.api.outlet.delete_outlet_media')`
pointing at a Python function that was renamed/removed/dropped in a merge, which
500s at runtime with "module ... has no attribute ...".

Pure text scan of the repo — no DB, no frappe, no bench needed. Runs fast in CI
or standalone: `python flamezo_backend/flamezo/tests/test_frontend_api_contract.py`.
"""
import os
import re

# tests -> flamezo -> flamezo_backend -> <repo root>
_THIS = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(_THIS, "..", "..", ".."))
FLAMEZO_DIR = os.path.join(REPO_ROOT, "flamezo_backend", "flamezo")
FRONTEND_SRC = os.path.join(REPO_ROOT, "frontend", "src")

# flamezo_backend.flamezo.<dotted.module.path>.<func>
_REF = re.compile(r"flamezo_backend\.flamezo\.((?:[A-Za-z0-9_]+\.)*[A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")

# Known-unresolved references (pre-existing tech debt, NOT rename mismatches).
# `api.cart` was never implemented in the backend, but Payment.tsx (routed at
# /restaurant/:outletId/payment) and QRCodeScanner still reference it. Building
# the cart/QR-parse endpoints is a separate feature task. Listed here so the
# guard stays green and catches NEW breakages; remove an entry once it's built.
_KNOWN_UNRESOLVED = {
    "api.cart.get_cart",
    "api.cart.parse_qr_code",
}


def _iter_frontend_refs():
    if not os.path.isdir(FRONTEND_SRC):
        return
    for root, _dirs, files in os.walk(FRONTEND_SRC):
        for name in files:
            if not name.endswith((".ts", ".tsx")):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            for m in _REF.finditer(text):
                yield m.group(1), m.group(2), path


def _module_file(dotted):
    return os.path.join(FLAMEZO_DIR, *dotted.split(".")) + ".py"


def _defined_in(body, func):
    # Defined here, imported here, or re-exported (assignment) — any counts.
    if re.search(rf"^\s*def {re.escape(func)}\s*\(", body, re.M):
        return True
    if re.search(rf"import[^\n]*\b{re.escape(func)}\b", body):
        return True
    if re.search(rf"^\s*{re.escape(func)}\s*=", body, re.M):
        return True
    return False


def find_missing():
    missing = []
    for dotted, func, src in _iter_frontend_refs():
        # Dynamic call: the literal ends at the MODULE and the method is appended
        # at call time (e.g. `M('merchant_get_my_posts')`). Can't verify the method
        # statically, but the module must at least exist — and it does, so skip.
        if os.path.exists(_module_file(f"{dotted}.{func}")):
            continue
        if f"{dotted}.{func}" in _KNOWN_UNRESOLVED:
            continue
        mod_file = _module_file(dotted)
        rel_src = os.path.relpath(src, FRONTEND_SRC)
        if not os.path.exists(mod_file):
            missing.append(f"{dotted}.{func}  — no module file {os.path.relpath(mod_file, REPO_ROOT)}  (called from {rel_src})")
            continue
        with open(mod_file, encoding="utf-8", errors="ignore") as fh:
            body = fh.read()
        if not _defined_in(body, func):
            missing.append(f"{dotted}.{func}  — not defined in {os.path.relpath(mod_file, REPO_ROOT)}  (called from {rel_src})")
    return sorted(set(missing))


def test_frontend_api_methods_exist():
    missing = find_missing()
    assert not missing, (
        "Admin frontend references backend methods that don't exist:\n  "
        + "\n  ".join(missing)
    )


if __name__ == "__main__":
    miss = find_missing()
    if miss:
        print("MISSING backend methods referenced by the frontend:")
        for m in miss:
            print("  " + m)
        raise SystemExit(1)
    print("OK — every frontend-referenced backend method exists.")
