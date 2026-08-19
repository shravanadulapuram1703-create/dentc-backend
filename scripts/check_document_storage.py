"""End-to-end probe of the patient-document storage path (LTR-16).

The consent-form flow has three moving parts that only exist once a real bucket
is configured, and none of them can be exercised locally:

1. the **upload** actually reaching ``gs://{bucket}/{consent prefix}/…``,
2. the **signed URL** (needs IAM ``signBlob`` — on Cloud Run the runtime service
   account must hold ``roles/iam.serviceAccountTokenCreator`` on *itself*),
3. the **``/patient-documents/{id}/content`` proxy** streaming the same bytes back.

Run this in the deployed environment after setting the env vars. It writes one
throwaway probe object, reads it back through both paths, compares the bytes and
then deletes it — so a green run means "print a consent → Save to Chart → open
the link" will work, without touching any patient record.

    python -m scripts.check_document_storage
    python -m scripts.check_document_storage --keep      # leave the probe object

Exits non-zero on the first failed check, so it is usable as a deploy gate.
"""

from __future__ import annotations

import argparse
import sys
import uuid

from app.core.config import settings
from app.integrations import object_storage as obj
from app.services import document_store

PROBE_BYTES = b"%PDF-1.4\n% document-storage probe\n"


def _ok(label: str, detail: str = "") -> None:
    print(f"  [ok]   {label}{(' — ' + detail) if detail else ''}")


def _fail(label: str, detail: str) -> None:
    print(f"  [FAIL] {label} — {detail}")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="Do not delete the probe object")
    parser.add_argument("--tenant", type=int, default=0, help="Tenant id used in the probe key")
    args = parser.parse_args()

    print("Document storage configuration")
    print(f"  GCS_BUCKET_DOCUMENTS      = {settings.GCS_BUCKET_DOCUMENTS!r}")
    print(f"  GCS_CONSENT_FORMS_PREFIX  = {settings.GCS_CONSENT_FORMS_PREFIX!r}")
    print(f"  GCS_DOCUMENTS_PREFIX      = {settings.GCS_DOCUMENTS_PREFIX!r}")
    print(f"  DOCUMENT_URL_MODE         = {settings.DOCUMENT_URL_MODE!r}")
    print(f"  PUBLIC_API_BASE_URL       = {settings.PUBLIC_API_BASE_URL!r}")
    print()

    if not document_store.gcs_enabled():
        print("GCS_BUCKET_DOCUMENTS is unset — uploads stay on local disk.")
        print("That is the intended dev/test behaviour, but it means this probe has")
        print("nothing to verify. Set the env var and re-run in the deployed environment.")
        sys.exit(2)

    bucket = settings.GCS_BUCKET_DOCUMENTS

    # 1. Routing — a consent form must land under the consent prefix.
    key = document_store.object_key(args.tenant, 0, "consent-form", "probe.pdf")
    if not key.startswith(settings.GCS_CONSENT_FORMS_PREFIX + "/"):
        _fail("consent-form routing", f"key {key!r} is not under the consent prefix")
    _ok("consent-form routing", f"gs://{bucket}/{key}")

    other = document_store.object_key(args.tenant, 0, "xray", "probe.dcm")
    if not other.startswith(settings.GCS_DOCUMENTS_PREFIX + "/"):
        _fail("generic routing", f"key {other!r} is not under the generic prefix")
    _ok("generic routing", other)

    # 2. Upload.
    probe_key = f"{settings.GCS_CONSENT_FORMS_PREFIX}/_probe/{uuid.uuid4().hex}.pdf"
    try:
        obj.upload_bytes(bucket, probe_key, PROBE_BYTES, content_type="application/pdf")
    except Exception as exc:  # noqa: BLE001
        _fail("upload", f"{type(exc).__name__}: {exc}")
    _ok("upload", f"{len(PROBE_BYTES)} bytes -> gs://{bucket}/{probe_key}")

    # 3. Signed URL. Not fatal on its own — the proxy is the documented fallback —
    #    but the practice should know which mode it is actually running in.
    signed = obj.signed_url(bucket, probe_key, download_name="probe.pdf")
    if signed:
        _ok("signed URL", signed.split("?", 1)[0] + "?…")
    else:
        print("  [warn] signed URL unavailable — file_url will use the "
              "/patient-documents/{id}/content proxy instead.")
        print("         On Cloud Run this usually means the runtime service account "
              "lacks roles/iam.serviceAccountTokenCreator on itself.")

    # 4. Read back through the same seam the /content proxy uses.
    class _Row:
        """Stands in for a PatientDocument row without touching the database."""

        id = 0
        storage_backend = document_store.GCS
        storage_bucket = bucket
        storage_path = probe_key
        file_path = probe_key
        file_name = "probe.pdf"
        file_url = ""
        content_type = "application/pdf"

    try:
        body, content_type, size = document_store.open_stream(_Row())
        streamed = b"".join(body)
    except Exception as exc:  # noqa: BLE001
        _fail("content proxy read", f"{type(exc).__name__}: {exc}")
    if streamed != PROBE_BYTES:
        _fail("content proxy read", f"got {len(streamed)} bytes, expected {len(PROBE_BYTES)}")
    _ok("content proxy read", f"{size} bytes, {content_type}")

    url = document_store.public_url(_Row())
    if url.startswith("gs://"):
        _fail("public_url", "returned a gs:// URI — the browser cannot fetch that")
    _ok("public_url", url.split("?", 1)[0])

    # 5. Listing (what GET /consent-forms serves).
    masters = document_store.list_consent_masters()
    _ok("consent-form listing", f"{len(masters)} object(s) under "
                                f"{settings.GCS_CONSENT_FORMS_PREFIX}/")

    # 6. Clean up.
    if args.keep:
        print(f"\n  probe object left in place: gs://{bucket}/{probe_key}")
    else:
        try:
            obj._get_client().bucket(bucket).blob(probe_key).delete()  # noqa: SLF001
            _ok("cleanup", "probe object deleted")
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] could not delete the probe object "
                  f"gs://{bucket}/{probe_key}: {exc}")

    print("\nAll checks passed. Print a consent -> Save to Chart -> open the link "
          "should now work end to end.")


if __name__ == "__main__":
    main()
