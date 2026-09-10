# Topaz signature pad — what has to happen outside the frontend code

The frontend change is complete and needs **no npm package, no bundled Topaz file and no server
component**. Everything else is per-workstation (the PC the pad is plugged into) plus the backend
columns in `topaz_signature_backend_devreport.md`.

## 1. Per workstation (every front-desk / operatory PC that will use a pad)

| # | Step | Notes |
|---|------|-------|
| 1 | Windows 10 or 11 (or Server 2012 R2+) with .NET Framework 4.8, and Chrome, Edge, Firefox or Opera | iPad / macOS / Android cannot use this integration — those users get on-screen signing automatically. |
| 2 | Plug in the Topaz pad (USB, "HSB" models). Serial/"BSB" models need the COM port set in Topaz's SigPlus tools. | Supported: T-LBK460/462/750/755/766, T-LBK43LC, T-LBK57GC, all "SE" models, GemView displays. |
| 3 | Download **SigPlusExtLite** (current 3.2.17.x) from <https://www.topazsystems.com/sdks/sigplusextlite.html> and run the installer **as Administrator**. | Installs the SigPlus drivers and the *Native Messaging Host* Windows service/app. Choose the pad model/connection when asked (HSB for USB). |
| 4 | Install the **Topaz SigPlusExtLite** browser extension in the browser used for DentC. | The installer registers it for Chrome/Edge/Firefox; if it does not appear, add it from the Chrome Web Store / Edge Add-ons / Firefox Add-ons ("Topaz SigPlusExtLite"). |
| 5 | Fully close and reopen the browser. | The extension injects `SigPlusExtLiteWrapperURL` into pages only after a restart. |
| 6 | In DentC open **Setup → Devices → Signature Pad (Topaz)**, press **Re-check**, and sign in the test box. | All five checks green + "Ready to sign" = done. The test signature is not saved. |
| 7 | (Optional) In Chrome/Edge extension settings, allow the extension **in Incognito / guest** profiles if staff use them. | Otherwise those windows silently fall back to on-screen signing. |

Group Policy / MDM shops: the extension can be force-installed via the `ExtensionInstallForcelist`
policy (Chrome / Edge) and the SigPlusExtLite MSI/EXE pushed silently with `/S` — Topaz's SDK page
has the silent-install switches.

## 2. Backend (dentc-backend)

- Implement the columns and request-body fields in `topaz_signature_backend_devreport.md` (SIG-1 → SIG-3
  first; they are the ones that lose data today).
- Nothing Topaz-specific runs on the server. Do **not** install SigPlus/SigWeb on the backend host.
- If HTTPS with a custom CA is used in the office, the extension is unaffected (it is local messaging), but
  the DentC origin must be `https://` in production — Chrome blocks some extension messaging on
  insecure origins other than `localhost`.

## 3. Nothing to do in the frontend deploy

- No new environment variable, no CDN script. The wrapper JS is served by the extension itself and loaded
  lazily by `src/features/signature/topaz/topazClient.ts` the first time a signature control mounts.
- Content-Security-Policy: if a CSP is added later, the extension's wrapper URL is
  `chrome-extension://<id>/…` / `moz-extension://…` and must be allowed in `script-src`.

## 4. How the app behaves without a pad

| Situation | What the user sees |
|-----------|--------------------|
| Extension not installed / non-Windows | Method toggle shows **On screen** selected, **Topaz pad** greyed with the reason in its tooltip; a grey "No Topaz pad" chip with a re-check button. Signing works exactly as before. |
| Software installed, pad unplugged | Chip says "Pad not detected"; still on-screen. Plug in and press ↻ — no reload needed. |
| Pad detected | **Topaz pad** is pre-selected; the box says "Please sign on the Topaz pad"; strokes stream live; DONE/ACCEPT enables once the pad reports points. |
| Pad unplugged mid-signature | Start fails → control drops to on-screen with the Topaz error shown; status is re-probed. |

## 5. Verifying a real pad (once hardware is available)

1. Diagnostics page → all checks green, model + serial shown.
2. Sign in the test box → "Method: Topaz pad", Points > 0, SigString length > 0.
3. Patient → Medical History → Signature tab → SIGN on the patient pad → DONE → Save. Then
   `GET /api/v1/patient-signatures?patient_id=<id>` shows `device_source: "topaz"` and a JPEG data URL.
4. Patient → Letters → sign a printed consent → outcome "Sign now" → Record. The consent row shows
   `signature_method: "topaz"`.
