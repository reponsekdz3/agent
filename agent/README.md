# NOVA-APEX Local Control Dashboard

NOVA-APEX is a Windows-hosted automation controller with a responsive browser dashboard. It can coordinate the configured browser, Windows desktop, Android ADB device, and files inside the configured workspace. It does **not** provide arbitrary access to every device or service.

## Safe setup

1. Use the existing virtual environment and install the dependencies from `requirements.txt` if needed:

   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

2. Copy `.env.example` to `.env`, set a unique `NOVA_APEX_AUTH_PASSWORD` of at least 16 characters, and retain the default `SERVER_HOST=127.0.0.1` for local-only use.
3. Start the dashboard:

   ```powershell
   python main.py --server
   ```

4. Open <http://127.0.0.1:8000>.

Dashboard authentication is required even for loopback use. The server refuses to start if the password is missing or too short. For authenticated access on a private network, retain `NOVA_APEX_COOKIE_SECURE=true` and configure the network edge as described below. Do not expose the controller directly to the public internet.

## Private remote access

Keep the application behind a VPN or other private access gateway and terminate HTTPS/TLS at a trusted reverse proxy. Bind the app only to the private interface reachable from that proxy (or `127.0.0.1` when the proxy is on the same machine); do not use a public-facing `0.0.0.0` binding without an intentionally secured private-network front end. The proxy must preserve the browser's `Host` and `Origin` values and forward WebSocket upgrades. Use a strong unique dashboard password and keep `NOVA_APEX_COOKIE_SECURE=true`; authenticated non-loopback startup refuses insecure cookies. Do not disable authentication or TLS to make remote access work.

The app uses an HttpOnly, SameSite=Strict session cookie, an expiring in-memory session, same-origin checks, and a CSRF token for state-changing API requests. Sessions are cleared on server restart. The dashboard password protects the controller; it does not protect an already compromised host or replace VPN, TLS, OS account security, or firewall rules.

## Dashboard and offline behavior

- The responsive PWA caches only the static application shell. API data and automation are not available offline.
- A mission queued while offline is stored locally in that browser's IndexedDB. It is not sent automatically: review and confirm each queued mission while the controller is reachable.
- Browser actions that click a page element, submit a form, or run page JavaScript require explicit confirmation. The engine pauses for review before consequential browser actions, including clicks that could place an order or book a reservation.
- Order, booking, and registration tasks are assisted workflows only: search, compare, and prepare a draft, then stop for user review. Final purchase, booking, payment, or submission is never autonomous.
- CAPTCHA and anti-bot bypass, automated OTP retrieval/injection, and automatic account submission are not supported.
- Workspace file access is limited to paths beneath `WORKSPACE_DIR`. The vault is protected with Windows DPAPI; retain access to the same Windows user profile to read it. Do not copy the vault to another account or machine as a backup.

## Configuration

See `.env.example` for the supported environment variables. Relevant settings:

- `SERVER_HOST` and `SERVER_PORT`: loopback by default; choose a private interface only when using authenticated private access over TLS.
- `NOVA_APEX_AUTH_PASSWORD`: required for all dashboard access; minimum 16 characters.
- `NOVA_APEX_COOKIE_SECURE`: keep `true` for HTTPS and all authenticated non-loopback access.
- `NOVA_APEX_SESSION_TTL_SECONDS`: session lifetime, minimum 60 seconds.
- `WORKSPACE_DIR`: workspace root for dashboard file operations.
- `ADB_ENABLED`, `ADB_DEVICE_ID`: optional Android Debug Bridge configuration.
- `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`: optional model-provider credentials. Use an appropriately scoped account and protect `.env`.

## Limits

NOVA-APEX runs on the configured Windows host; the dashboard is a remote control surface, not a native cross-platform agent. Device actions require the relevant host tools and explicit device authorization. External sites may require human verification and may change their interfaces. Offline mode only preserves the app shell and a user-reviewed local queue; it cannot perform online tasks or guarantee access to local devices when the controller is unavailable.

Do not use the controller to access devices, accounts, websites, or files without authorization.
