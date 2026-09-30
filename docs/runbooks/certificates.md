# Certificate trust

The station serves the console over HTTPS with a certificate from **its own certificate
authority**: Caddy's internal CA, created on first start. The field has no Internet, so no
public CA can issue one. Each operator device trusts that CA **once**; after that, the
browser shows the station as secure, with no warning to click through. This matters:
clicking through a warning teaches people to ignore the one that means an attack.

## 1. Get the station's root certificate

On the station:

```bash
docker compose -f deploy/compose.yaml exec -T console \
  cat /data/caddy/pki/authorities/local/root.crt > sar-gcs-root.crt
sha256sum sar-gcs-root.crt      # write the fingerprint down; compare it on each device
```

The CA persists in the `caddy-data` volume: reinstalls and upgrades keep it, so devices
stay trusted. Deleting the volume (`down -v`) creates a new CA, and every device must
trust it again.

## 2. Install it on each device

Copy `sar-gcs-root.crt` by USB stick or the station's LAN (never by a public service), check
the fingerprint, then:

| Device | How |
|---|---|
| Windows | Double-click the file → **Install certificate** → Local machine → *Trusted Root Certification Authorities*. Restart the browser. |
| macOS | Double-click → Keychain *System* → open it → **Trust: Always Trust**. |
| Linux (Chrome/Edge) | `sudo cp sar-gcs-root.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates`; Chrome: Settings → Privacy → Security → Manage certificates → Authorities → Import. |
| Android | Settings → Security → Encryption & credentials → Install a certificate → CA certificate. |
| iPad / iPhone | Open the file → Settings → Profile downloaded → Install; then Settings → General → About → Certificate Trust Settings → enable it. |

## 3. Check

Open `https://<SARGCS_SITE_ADDRESS>/`: a padlock, no warning. If the browser warns, check:

- the address typed is exactly `SARGCS_SITE_ADDRESS` (the certificate is issued for it);
- the device's clock is right (certificates have validity dates);
- the fingerprint matches the station's.

If the station's address changes, set `SARGCS_SITE_ADDRESS` and restart the console
container: Caddy issues a new certificate from the same CA, so devices need nothing new.
