# Report A — Pricing data completeness (folder → DB)

**Question:** for every data point the fee-schedule calculation needs, is it present
in the DB (ingested from the export folder), and what is in the folder but **not**
ingested?

**Source folder:** `F:\Recon Dental Data\Data Migration\Data Migration`
**Method:** read-only. Each pricing input is counted in the export folder and in the
DB and compared. Reproduce with:

```bash
python -m scripts.report_pricing_data_completeness
```

---

## 1. Folder vs DB, per pricing input

| Pricing input | Folder | DB | Gap (folder − DB) | Reading |
|---|--:|--:|--:|---|
| Fee schedule headers (FeeScheH) | 36 | 47 | −11 | DB has more (app/test lists) — OK |
| Fee schedule entries (FeeScheD) | 13,488 | 13,493 | −5 | OK — all ingested |
| Fee schedule assignments (FeeScheA) | 2 | 17 | −15 | DB has more (office/carrier backfill) — OK |
| Offices with a UCR list (Office.FEEID) | 15 | 16 | −1 | all 15 ingested — OK |
| Offices with a default list (Office.PATIENTFEEID) | 8 | 17 | −9 | backfill filled the rest — OK |
| Patients with a fee schedule (PATIENT.FEESCHEDULE) | 79,079 | 79,112 | −33 | all ingested — OK |
| Carriers with a fee list (Carrier.FEEID) | 13 | 15 | −2 | OK |
| Insurance plans (InsPlans) | 31,328 | 31,337 | −9 | OK |
| Coverage rules (INSCOVERAGE) | 876,927 | 876,901 | **26** | 26 rules not ingested |
| Patient insurance slots (PatInsPlans) | 56,086 | 55,121 | **965** | 965 slots not ingested |
| &nbsp;&nbsp;…secondary slots (INSTYPE=S) | 954 | 1 | **953** | **COB coverage missing** (s19 read the wrong column) |
| &nbsp;&nbsp;…remaining deductible (INDDEDREM>0) | 12,467 | 3 | **12,464** | **actual remaining deductible missing** |
| Charges (LEDGER, LTYPE=C only) | 1,447,972 | 1,372,620 | **75,352** | 75k charge rows have no `patient_procedures` row |
| &nbsp;&nbsp;…of which AMOUNT=0 in the SOURCE | 1,097,174 | 1,021,760 | — | **source limitation, see §3** |
| Per-charge provenance (LEDGERINSD) | 1,447,969 | 1,360,384 | 87,585 | loaded now; gap = the 75k un-ingested charges + ~12k charges with no LEDGERINSD row |
| Procedure codes (Codes) | 1,108 | 1,122 | −14 | OK |
| &nbsp;&nbsp;…codes with a coverage_category | — | 722 | — | **386 codes have no coverage band** |

A **negative gap** means the DB holds more than the folder — expected for
app-created rows, the test offices, and the office/carrier backfill. Those are not
gaps. The rows in **bold** are the real gaps to act on.

---

## 2. Ingestion gaps to fix (folder has data the DB does not)

Ranked by pricing impact:

1. **Secondary insurance slots — 953 not ingested** (`PatInsPlans.INSTYPE='S'`; DB has 1).
   Without them there is **no coordination-of-benefits (secondary) coverage** for
   those patients, so the split under-credits insurance. Root cause: the migration
   step `s19` read a column that does not exist.
2. **Remaining deductible — 12,464 not ingested** (`PatInsPlans.INDDEDREM>0`; DB has 3).
   The split falls back to the *plan's* full deductible instead of the patient's
   actual remaining, so the patient/insurance portions are off for insured patients
   mid-deductible.
3. **Charges — 75,352 folder rows have no `patient_procedures` row** (LTYPE='C':
   1,447,972 in folder vs 1,372,620 in DB). Likely voided / archived charges or
   charges whose patient was not migrated, but it should be confirmed and, where
   valid, re-ingested — those charges cannot be priced or validated at all today.
4. **Patient insurance slots — 965 total not ingested** (superset of the 953 secondary).
5. **Coverage rules — 26 not ingested.** A handful of plans are missing a band.
6. **Procedure codes without a coverage band — 386** (722 of 1,108 have one).
   A code with no `coverage_category` gets **0 % insurance**, so any charge for one
   of those codes splits entirely to the patient.

The per-patient CSV of gaps is attached (`unpriceable_patients.csv`) — only **2**
ingested patients are missing a piece (an insured patient whose plan carries no
coverage rules), so the fee tier itself is essentially complete (see §4).

---

## 3. Source-data limitation (NOT an ingestion bug — cannot be fixed by re-ingesting)

**1,097,174 charge rows carry `AMOUNT = 0.0000` in the export itself.** The real fee
is only in the free-text note, e.g. a 2013 charge:

```
"...","10344603",...,"C",...,"D0120",...,"$30 periodic oral evaluation - established patient",...,"0.0000"
```

The DB faithfully stored `fee = 0` because that is what the source `AMOUNT` says.
This is concentrated in **older charges** and rises monotonically with age:

| Year | charges | fee=0 |
|---|--:|--:|
| 2026 | 5,451 | 8.4 % |
| 2025 | 63,044 | 19.3 % |
| 2024 | 62,351 | 26.9 % |
| 2022 | 76,166 | 33.1 % |
| 2020 | 58,997 | 50.7 % |
| 2017 | 53,877 | 69.3 % |
| 2015 | 46,715 | 90.9 % |
| 2014 and earlier | — | ~100 % |

**Implication:** ~1.02M migrated charges have no structured fee to price against or
validate. They can only be recovered by parsing the dollar figure out of the note
text (`"$30 …"`) — a lossy heuristic — if that is wanted at all. This is the single
biggest reason Report B can only *validate* the ~350k charges that carry a real fee.

---

## 4. Per-patient priceability (patients with ≥1 charge)

| Metric | Count |
|---|--:|
| Patients with a charge | 68,010 |
| Have a fee source (patient list / office default / office UCR) | 68,010 (100 %) |
| Have a home office | 68,010 (100 %) |
| Insured (≥1 active plan slot) | 50,086 |
| Insured **and** the plan has coverage rules | 50,084 |
| Missing a piece to price | **2** |

**Every ingested patient can be fee-priced.** The only per-patient gap is 2 insured
patients whose plan carries no coverage rules (they price fee-correct, insurance 0).

---

## What to do next

Re-run the migration/ingestion to fill items 1–6 in §2 (the secondary slots and the
remaining-deductible are the highest-value for the split), decide whether the §3
note-embedded fees are worth recovering, then re-run **Report B** to re-measure
calculation correctness on the enlarged, corrected dataset.
