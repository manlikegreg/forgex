# Code Signing with ForgeX

ForgeX supports both commercial and **free self-signed code signing** for Windows executables.

## Why Code Sign?

- **Authenticity**: Proves the executable came from you
- **Integrity**: Detects if the file has been tampered with
- **Reduced AV False Positives**: Signed executables are less likely to be flagged
- **Professional**: Shows legitimacy to users

## Self-Signed Certificate (FREE)

ForgeX can automatically generate and use self-signed certificates using OpenSSL.

### Requirements

- **OpenSSL** must be installed and in PATH
- **Windows SDK** (for `signtool.exe`)

#### Install OpenSSL on Windows

```powershell
# Using Chocolatey
choco install openssl

# Or download from: https://slproweb.com/products/Win32OpenSSL.html
```

#### Verify Installation

```bash
openssl version
signtool /?
```

### Usage

In your build request, enable self-signed code signing:

```json
{
  "language": "python",
  "start_command": "uvicorn main:app --host 0.0.0.0 --port 8000",
  "output_type": "exe",
  "code_sign": {
    "enable": true,
    "generate_self_signed": true,
    "self_signed_cn": "My Company Name",
    "self_signed_valid_days": 365,
    "description": "My Application",
    "publisher": "https://mycompany.com"
  }
}
```

### Parameters

- `enable`: Set to `true` to enable code signing
- `generate_self_signed`: Set to `true` to auto-generate a certificate
- `self_signed_cn`: Your company/app name (appears as "Common Name")
- `self_signed_valid_days`: Certificate validity period (default: 365)
- `description`: Friendly name shown in Windows prompts
- `publisher`: URL shown in certificate details
- `timestamp_url`: RFC 3161 timestamp server (default: DigiCert)

## Commercial Certificate

If you have a purchased code signing certificate (e.g., from DigiCert, Sectigo):

```json
{
  "code_sign": {
    "enable": true,
    "cert_path": "C:/path/to/certificate.pfx",
    "cert_password": "your-cert-password",
    "description": "My Application",
    "publisher": "https://mycompany.com"
  }
}
```

## Trust & SmartScreen

### Self-Signed Certificates

⚠️ **Important**: Self-signed certificates are **NOT trusted by default**. Windows SmartScreen will show warnings until:

1. **Build Reputation**: The more users run your signed app, the better its reputation
2. **Manual Trust** (for testing):
   ```powershell
   # Import the generated certificate to Trusted Root (Admin required)
   certutil -addstore "TrustedPublisher" forgex_selfsigned.pfx
   ```

### Commercial Certificates

- Instantly trusted by Windows
- No SmartScreen warnings (after initial reputation building)
- Cost: $50-400/year

## Benefits of Self-Signed vs. Unsigned

Even though self-signed certs aren't automatically trusted, they provide:

✅ **Tamper Detection**: Any modification breaks the signature
✅ **Identity**: Users can verify the signature matches across downloads
✅ **AV Heuristics**: Some antiviruses are less suspicious of signed binaries
✅ **Professional Appearance**: Shows you took security seriously

## Troubleshooting

### "OpenSSL not found"

Ensure OpenSSL is in PATH:
```powershell
$env:PATH += ";C:\Program Files\OpenSSL-Win64\bin"
```

### "signtool not found"

Install Windows SDK:
- Download: https://developer.microsoft.com/windows/downloads/windows-sdk/
- Or install via Visual Studio Installer

### Timestamp Failures

If timestamping fails (network issues), the signature will still work but won't be verifiable after certificate expiration. The build will continue with a warning.

## Example: Python FastAPI App

```json
{
  "project_path": "/path/to/project",
  "language": "python",
  "start_command": "uvicorn main:app --host 0.0.0.0 --port 8000",
  "output_type": "exe",
  "output_name": "MyServer",
  "code_sign": {
    "enable": true,
    "generate_self_signed": true,
    "self_signed_cn": "MyServer by ACME Corp",
    "self_signed_valid_days": 730,
    "description": "MyServer Backend Service",
    "publisher": "https://acme.example.com"
  },
  "pyinstaller": {
    "noconsole": true
  }
}
```

## What Happens Behind the Scenes

1. **Key Generation**: Creates a 2048-bit RSA private key
2. **Certificate Creation**: Generates an X.509 self-signed certificate
3. **PFX Conversion**: Converts to PKCS#12 format for signtool
4. **Signing**: Uses Windows SDK `signtool` with SHA256
5. **Timestamping**: Adds RFC 3161 timestamp for long-term validity
6. **Cleanup**: Removes intermediate files, keeps only the signed EXE

## Security Notes

- 🔒 Private keys are generated fresh for each build and stored temporarily
- 🔒 PFX passwords are randomized and kept in-memory only
- 🔒 Sensitive files are cleaned up after signing
- ⚠️ For production: use a **commercial certificate** for automatic trust

## Next Steps

After signing:
1. Test the signature: Right-click EXE → Properties → Digital Signatures
2. Verify it shows your Common Name
3. Distribute and build reputation with users
4. Consider upgrading to a commercial cert for production releases
