# Google OAuth Setup (Calendar)

A non-technical step-by-step for granting Calendar Photo Organizer read-only
access to your Google Calendar. Only Calendar scopes are requested for the
default install (Constitution Principle II).

## 1. Create a Google Cloud project

1. Visit <https://console.cloud.google.com/projectcreate>.
2. Enter a project name (e.g. `calendar-photo-organizer-local`) and click **Create**.
3. Wait for the project to be created and ensure it is selected in the top bar.

## 2. Enable the Google Calendar API

1. Open <https://console.cloud.google.com/apis/library/calendar-json.googleapis.com>.
2. Click **Enable**.

## 3. Configure the OAuth consent screen

1. Open <https://console.cloud.google.com/apis/credentials/consent>.
2. Choose **External**, then **Create**.
3. Fill in:
   - **App name**: Calendar Photo Organizer (Local)
   - **User support email**: your own email
   - **Developer contact email**: your own email
4. Click **Save and Continue**.
5. On **Scopes**: click **Add or Remove Scopes**, search for `calendar.readonly`,
   tick `https://www.googleapis.com/auth/calendar.readonly`, click **Update**,
   then **Save and Continue**.
6. On **Test users**: add your own Google email so the app can be used while in
   `Testing` mode. Save and continue.

## 4. Create OAuth client credentials

1. Open <https://console.cloud.google.com/apis/credentials>.
2. Click **Create Credentials → OAuth client ID**.
3. **Application type**: **Desktop app**. Name it `cpo-desktop`.
4. Click **Create**, then **Download JSON**.
5. Save the file as `~/.config/calendar-photo-organizer/credentials.json` (Linux/macOS)
   or `%APPDATA%\calendar-photo-organizer\credentials.json` (Windows).

## 5. Run the local OAuth flow

```bash
cpo auth google-calendar
```

A browser window opens — sign in with the same Google account you added as a
test user. After consent, the refresh token is stored in your OS keychain
(macOS Keychain, Windows Credential Manager, or Linux Secret Service).

## Revoking access

Visit <https://myaccount.google.com/permissions> and remove the
"Calendar Photo Organizer (Local)" app.

## Troubleshooting

- **"redirect_uri_mismatch"**: ensure the credential is a **Desktop app** type;
  do not use a Web application credential.
- **"access blocked: this app is not verified"**: while in **Testing** mode you
  must add your own email under **Test users**.
- **Exit code 3 from `cpo`**: the stored refresh token has expired or been
  revoked; rerun `cpo auth google-calendar`.
