# Code Signing Guide — Genesis Companion

## Overview

The GitHub Actions workflow is pre-wired for signing.
All you need to do is add the secrets and certificates when ready.

---

## Windows — Authenticode Signing

### Option A: EV Code Signing Certificate (recommended for SmartScreen)
**Cost:** ~$300–700/year from DigiCert, Sectigo, or GlobalSign.
**Result:** No SmartScreen warning; highest user trust.

**Steps:**
1. Purchase an EV cert from a CA (DigiCert preferred).
2. Export the cert as `.pfx` (base64 encode it):
   ```bash
   base64 -i certificate.pfx | tr -d '\n' > cert_b64.txt
   ```
3. Add to GitHub Secrets:
   - `WINDOWS_CERTIFICATE` — the base64 string from step 2
   - `WINDOWS_CERTIFICATE_PASSWORD` — your PFX password

4. The workflow's Tauri action reads `TAURI_SIGNING_PRIVATE_KEY` for updater
   signing (separate from Authenticode). Generate with:
   ```bash
   npx tauri signer generate -w ~/.tauri/myapp.key
   ```
   Then add:
   - `TAURI_SIGNING_PRIVATE_KEY` — content of `myapp.key`
   - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` — your chosen password

### Option B: Self-Signed (dev/internal use only)
**Result:** SmartScreen "Unknown Publisher" warning appears. Not for distribution.
```bash
# PowerShell — creates self-signed cert for dev testing
$cert = New-SelfSignedCertificate -Type CodeSigningCert `
  -Subject "CN=Genesis Companion Dev" `
  -CertStoreLocation Cert:\CurrentUser\My
```

---

## macOS — Notarization

**Requirements:**
- Apple Developer Program membership ($99/year)
- Mac with Xcode installed (for initial cert creation)

**Steps:**
1. In Xcode → Settings → Accounts → Manage Certificates:
   - Create a "Developer ID Application" certificate.
   - Export as `.p12` with a strong password.
   - Base64 encode: `base64 -i cert.p12 | tr -d '\n'`

2. Create an app-specific password at appleid.apple.com.

3. Add to GitHub Secrets:
   - `APPLE_CERTIFICATE` — base64 of your `.p12`
   - `APPLE_CERTIFICATE_PASSWORD` — your `.p12` export password
   - `KEYCHAIN_PASSWORD` — any password (used to create temporary keychain in CI)
   - `APPLE_ID` — your Apple ID email
   - `APPLE_PASSWORD` — the app-specific password from step 2
   - `APPLE_TEAM_ID` — your 10-char team ID (from developer.apple.com)

**Result:** App passes Gatekeeper; no "unidentified developer" warning.

---

## Tauri Updater Signing (required for auto-update)

The updater uses Ed25519 to verify update signatures.
This is separate from OS-level code signing.

```bash
# Generate the key pair (run once, save the key securely)
npx tauri signer generate -w ~/.tauri/genesis-companion.key

# Output:
#   Private key written to ~/.tauri/genesis-companion.key
#   Public key: <base64 pubkey>
```

1. Copy the **public key** into `tauri.conf.json`:
   ```json
   "plugins": {
     "updater": {
       "pubkey": "<paste public key here>",
       ...
     }
   }
   ```
   (Replace `PLACEHOLDER_UPDATE_PUBKEY`)

2. Add to GitHub Secrets:
   - `TAURI_SIGNING_PRIVATE_KEY` — content of `~/.tauri/genesis-companion.key`
   - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` — key password (can be empty string)

---

## GitHub Secrets Checklist

| Secret | Required for | Notes |
|--------|-------------|-------|
| `TAURI_SIGNING_PRIVATE_KEY` | Auto-update | Ed25519 private key |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Auto-update | Can be empty |
| `APPLE_CERTIFICATE` | macOS signing | base64 .p12 |
| `APPLE_CERTIFICATE_PASSWORD` | macOS signing | .p12 export password |
| `KEYCHAIN_PASSWORD` | macOS signing | Temp keychain |
| `APPLE_ID` | macOS notarize | Apple ID email |
| `APPLE_PASSWORD` | macOS notarize | App-specific password |
| `APPLE_TEAM_ID` | macOS notarize | 10-char team ID |
| `VSCE_PAT` | VS Code publish | Personal Access Token |

**Without these secrets:** The workflow still runs and produces artifacts,
but binaries will be unsigned and auto-update won't work.
