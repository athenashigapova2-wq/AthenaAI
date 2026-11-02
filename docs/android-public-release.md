# Android public release

The debug APK is only for device testing. Public distribution must use the
signed artifacts produced by the `Android signed release` GitHub Actions
workflow.

## One-time signing setup

Create and protect one release keystore outside the repository. Losing it can
prevent future updates from being installed over the published app. Add these
GitHub Actions secrets:

- `ANDROID_KEYSTORE_BASE64`: base64-encoded keystore bytes;
- `ANDROID_KEYSTORE_PASSWORD`;
- `ANDROID_KEY_ALIAS`;
- `ANDROID_KEY_PASSWORD`;
- `VITE_SUPABASE_URL`;
- `VITE_SUPABASE_ANON_KEY`.

Never commit the keystore or passwords. Keep an encrypted offline backup of the
keystore and recovery information.

## Build

Run `Android signed release` manually on `main` and provide:

- the stable public HTTPS FastAPI origin;
- a `version_code` greater than every previously distributed build;
- a user-facing `version_name`, for example `1.0.0`.

The workflow refuses missing signing inputs, verifies backend readiness and
CORS, runs the frontend build, Capacitor sync, Android `lintRelease`, creates a
signed APK and AAB, verifies both signatures, and publishes SHA-256 checksums.

Use the APK for direct installation and the AAB for Google Play. Do not publish
the debug APK.

## Release gate

Before sharing an artifact publicly:

1. Confirm all CI jobs pass on the exact commit.
2. Verify the downloaded artifact against `android-release-sha256.txt`.
3. Install the signed APK on a clean physical device.
4. Complete the ten-pass Android acceptance flow without changing the APK or
   backend revision.
5. Verify signup, login, logout/login persistence, password reset, OAuth return,
   account deletion re-authentication, meal write confirmation/read-back,
   workout logging, meal suggestions, cycle localization, offline/retry states,
   and update installation over the previous signed release.
6. Publish the privacy policy and a support contact alongside the download.

The artifact is not release-ready until the signing secrets exist and this gate
passes for the exact APK checksum.
