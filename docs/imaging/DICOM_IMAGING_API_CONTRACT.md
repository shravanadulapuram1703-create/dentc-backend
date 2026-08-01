# Patient Imaging (DICOM) — Backend API Contract

**Audience:** frontend team wiring the **X-ray / Images** tab
(`/patient/{patientId}/imaging`, e.g. `http://localhost:5173/patient/74115/imaging`).

This document is the complete contract for loading a patient's scanned images
(migrated from the legacy Apteryx PACS into GCS + Postgres) and rendering them.
Everything is snake_case. Base path: **`/api/v1`**.

---

## 1. TL;DR — how it works

1. Call **`GET /api/v1/patients/{patient_id}/imaging`** with the user's bearer
   token. You get a **study → series → instance** tree.
2. Each instance carries an **`assets`** object with **ready-to-use URLs**
   (`thumbnail_url`, `web_url`, `original_url`).
3. Drop those URLs **straight into `<img src>` / download links**. They are
   absolute-relative (`/api/v1/dicom-instances/...?token=...`), **self-authorising
   (no Authorization header needed)**, and safe to use in `<img>` tags.
4. Render `thumbnail_url` in the gallery grid; on click, open `web_url` in the
   viewer; offer `original_url` as a "Download DICOM" link.
5. If an image's derivatives aren't generated yet, its `assets.status` is
   `"pending"` and the relevant URL is `null` — show a spinner/placeholder.

That's the whole integration. Details below.

---

## 2. Authentication

- **Tree + metadata endpoints** (`/patients/{id}/imaging`, `/dicom-instances/{sop}`):
  standard **`Authorization: Bearer <access_token>`**, same as every other API
  call. Tenant is resolved from the token (super-admins may pass `X-Tenant-ID`).
- **Binary/asset endpoints** (`/dicom-instances/{sop}/thumbnail|web|original`):
  **no Authorization header** — they authorise via the `?token=...` embedded in
  the URLs the tree already gave you. This is what lets them work inside `<img>`.
  You never build these URLs yourself; always use the ones from the response.

---

## 3. Endpoints

### 3.1 `GET /patients/{patient_id}/imaging`  — the main call

The full imaging tree for one patient.

**Path params:** `patient_id` (int) — the internal patient id (the `74115` in the URL).

**Query params (all optional):**

| Param | Type | Meaning |
|---|---|---|
| `modality` | string | Filter to a modality: `IO` (intra-oral), `PX` (pano), `XC` (photo/imported) |
| `tooth` | int | Only instances tagged with this tooth number |
| `date_from` | string `YYYY-MM-DD` | Studies on/after this date |
| `date_to` | string `YYYY-MM-DD` | Studies on/before this date |

**200 response** (`PatientImagingResponse`):

```jsonc
{
  "patient_id": 74115,
  "study_count": 2,
  "image_count": 9,
  "latest_study_date": "2019-11-13",
  "studies": [
    {
      "id": 1,
      "study_instance_uid": "1.2.840.114384.0.2019.11.13.15.52.3.44",
      "study_date": "2019-11-13",
      "study_time": "155135",
      "description": "FMX",
      "accession_number": null,
      "modalities": ["IO"],
      "identity_review_required": false,
      "image_count": 5,
      "series": [
        {
          "id": 1,
          "series_instance_uid": "1.2.840.114384.0.2019.11.13.15.52.3.44",
          "modality": "IO",
          "series_number": "1",
          "body_part": null,
          "description": null,
          "instances": [
            {
              "id": 10,
              "sop_instance_uid": "1.2.840.114384.0.2019.11.13.15.52.6.50",
              "sop_class_uid": "1.2.840.10008.5.1.4.1.1.7",
              "instance_number": "1",
              "modality": "IO",
              "rows": 1368,
              "columns": 1896,
              "bits_allocated": 8,
              "photometric_interpretation": "MONOCHROME2",
              "window_center": null,
              "window_width": null,
              "tooth_numbers": [18],
              "anatomic_codes": ["T-54210"],
              "derivative_status": "ready",
              "has_original_attributes": false,
              "assets": {
                "status": "ready",
                "thumbnail_url": "/api/v1/dicom-instances/1.2.840.../thumbnail?token=eyJ...",
                "web_url": "/api/v1/dicom-instances/1.2.840.../web?token=eyJ...",
                "original_url": "/api/v1/dicom-instances/1.2.840.../original?token=eyJ..."
              }
            }
          ]
        }
      ]
    }
  ]
}
```

- **Empty state:** a patient with no imaging returns `study_count: 0`,
  `image_count: 0`, `studies: []` (HTTP 200, not 404).
- **Unknown patient:** HTTP 404 with the standard error envelope.
- Studies are ordered newest-first; instances by `instance_number`.

### 3.2 `GET /patients/{patient_id}/imaging/summary` — counts for the tab badge

Lightweight; use it for the tab label/badge or the Patient Overview card without
pulling the whole tree.

```jsonc
{
  "patient_id": 74115,
  "study_count": 2,
  "image_count": 9,
  "latest_study_date": "2019-11-13",
  "modalities": ["IO", "PX"],
  "pending_derivatives": 3     // images whose web JPEG isn't generated yet
}
```

### 3.3 `GET /dicom-instances/{sop_instance_uid}` — single-image metadata

Returns one `DicomInstanceOut` (same shape as an instance in the tree, including
a fresh `assets` block). Useful for a deep-linked/standalone viewer. Bearer auth.

### 3.4 Binary/asset endpoints (used via the URLs from `assets`)

| Endpoint | Returns |
|---|---|
| `GET /dicom-instances/{sop}/thumbnail?token=…` | Small preview JPEG |
| `GET /dicom-instances/{sop}/web?token=…` | Full-resolution web JPEG |
| `GET /dicom-instances/{sop}/original?token=…` | Original `.dcm` (DICOM download) |

Behaviour: the server either **307-redirects** to a short-lived Google Cloud
Storage signed URL (production) or **streams the bytes** directly (dev). Either
way the browser just follows it — **you do nothing special**, put the URL in an
`<img>` / `<a download>`. Every access is logged to the HIPAA audit trail.

- `200` (or a transparent `307`→`200`): the image bytes.
- `404` `{ "error": { "code": "asset_not_ready" } }`: derivative not generated yet.
- `401` `{ "error": { "code": "invalid_image_token" } }`: the token expired
  (default lifetime **24h**). Re-fetch the tree to get fresh URLs.

---

## 4. Derivative status — what to render when

Browsers **cannot display raw DICOM/JPEG-2000**, so the backend serves generated
**JPEG derivatives**. Two are produced per image: a **thumbnail** (eager, made for
every image up front) and a **full-resolution web** JPEG (generated on first view,
then cached). `assets.status` tells you what exists right now:

| `assets.status` | thumbnail_url | web_url | original_url | Render as |
|---|---|---|---|---|
| `"ready"` | url | url | url | Thumb in grid; web JPEG in viewer |
| `"pending"` | url **or** null | null | url | Thumb if present, else placeholder; viewer shows "preparing…" |
| `"failed"` | maybe | null | url | Placeholder + "preview unavailable"; still offer DICOM download |

**Rule of thumb:** use `thumbnail_url` when non-null for the grid; use `web_url`
for the full viewer; if `web_url` is null, show the thumbnail scaled up (or a
spinner) and optionally re-poll `GET /dicom-instances/{sop}` — the web JPEG is
generated on demand and typically appears within a few seconds.

`original_url` (the `.dcm`) is for **download only** — do not put it in `<img>`.

---

## 5. TypeScript types

```ts
export interface InstanceAssets {
  status: "ready" | "pending" | "failed";
  thumbnail_url: string | null;
  web_url: string | null;
  original_url: string | null;
}

export interface DicomInstanceOut {
  id: number;
  sop_instance_uid: string;
  sop_class_uid: string | null;
  instance_number: string | null;
  modality: string | null;
  rows: number | null;
  columns: number | null;
  bits_allocated: number | null;
  photometric_interpretation: string | null;
  window_center: string | null;
  window_width: string | null;
  tooth_numbers: number[] | null;
  anatomic_codes: string[] | null;      // raw SNOMED SNM3 tooth codes
  derivative_status: string;
  has_original_attributes: boolean;      // legacy header was re-identified ("CORRECT")
  assets: InstanceAssets;
}

export interface DicomSeriesOut {
  id: number;
  series_instance_uid: string;
  modality: string | null;
  series_number: string | null;
  body_part: string | null;
  description: string | null;
  instances: DicomInstanceOut[];
}

export interface DicomStudyOut {
  id: number;
  study_instance_uid: string;
  study_date: string | null;            // YYYY-MM-DD
  study_time: string | null;
  description: string | null;
  accession_number: string | null;
  modalities: string[] | null;
  identity_review_required: boolean;
  image_count: number;
  series: DicomSeriesOut[];
}

export interface PatientImagingResponse {
  patient_id: number;
  study_count: number;
  image_count: number;
  latest_study_date: string | null;
  studies: DicomStudyOut[];
}

export interface PatientImagingSummary {
  patient_id: number;
  study_count: number;
  image_count: number;
  latest_study_date: string | null;
  modalities: string[];
  pending_derivatives: number;
}
```

The endpoints are OpenAPI-tagged **`Imaging`** with these `operation_id`s, so
Orval generates: `getPatientImaging`, `getPatientImagingSummary`,
`getDicomInstance`, `getDicomThumbnail`, `getDicomWebImage`,
`downloadDicomOriginal`.

---

## 6. Suggested UI wiring

```tsx
// 1) load the tree
const { data } = useGetPatientImaging(patientId);

// 2) flatten to a gallery (or keep the study/series grouping for accordions)
const images = data.studies.flatMap(s =>
  s.series.flatMap(se => se.instances.map(i => ({ ...i, study: s })))
);

// 3) grid — thumbnails
{images.map(img => (
  <button key={img.sop_instance_uid} onClick={() => openViewer(img)}>
    {img.assets.thumbnail_url
      ? <img src={img.assets.thumbnail_url} alt={img.modality ?? "image"} loading="lazy" />
      : <Placeholder status={img.assets.status} />}
  </button>
))}

// 4) viewer — full-res web JPEG (fall back to thumbnail while pending)
<img src={selected.assets.web_url ?? selected.assets.thumbnail_url ?? undefined} />

// 5) download original DICOM
{selected.assets.original_url &&
  <a href={selected.assets.original_url} download>Download DICOM</a>}
```

- **Group by study** in the UI (each study = a visit/date). `study.description`
  and `study.modalities` make good section headers.
- **Badges:** show `identity_review_required` (data-quality: this study's
  patient identity needs review) and `has_original_attributes` (the legacy image
  was re-identified) if you want to surface data provenance.
- **Filters:** wire modality/tooth/date filters to the query params in §3.1.
- **Token refresh:** asset URLs carry a 24h token. For long-lived open tabs, if
  an image 401s, just re-run `getPatientImaging` to refresh all URLs.

---

## 7. Errors

Every failure uses the app-wide envelope:

```json
{ "error": { "code": "not_found", "message": "Patient '55555' was not found", "details": null } }
```

Codes you may hit: `not_found` (unknown patient/instance), `unauthorized`
(missing/expired bearer), `invalid_image_token` / `image_token_mismatch`
(stale asset URL — refetch the tree), `asset_not_ready` (derivative pending).

---

## 8. Current status / what to expect in each environment

- **The API is live and stable**, and the first migrated sample is already
  loaded and rendering. Good patients to test against:
  - **patient `12903`** (Jessica Johnson) — 2 studies, 9 images, all `ready`.
  - **patient `74115`** (Kevin Seidl) — no imaging → the empty state
    (`studies: []`), which is what to design for first.
- Images appear after the backend pipeline runs for a patient: migration
  (index + originals→GCS) → promote (staging→`dicom_*`) → derivative worker
  (thumbnail/web JPEGs). Until derivatives exist for an image its
  `assets.status` is `pending`; the tree/metadata are populated regardless, so
  every layout/loading/empty state is testable now.
- **No frontend change is needed** as more patients are migrated — the contract
  above is final.

---

## 9. Backend reference (for questions)

| Piece | File |
|---|---|
| Endpoints | `app/api/v1/imaging.py` |
| Read/serve logic | `app/services/imaging_service.py` |
| Object storage / signed URLs / asset tokens | `app/integrations/object_storage.py` |
| Response schemas | `app/schemas/imaging.py` |
| Tables | `app/db/models/imaging.py` (`DicomStudy/Series/Instance`, `StoredObject`) |
| Migration | `alembic/versions/f2a3b4c5d6e7_add_dicom_archive_tables.py` |
| Config (buckets, TTLs) | `app/core/config.py` (`GCS_*`, `IMAGING_*`) |
