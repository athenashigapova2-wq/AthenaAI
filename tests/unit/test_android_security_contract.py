import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_android_release_surface_requires_secure_transport() -> None:
    capacitor = (ROOT / "capacitor.config.ts").read_text(encoding="utf-8")
    manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")

    assert "androidScheme: 'https'" in capacitor
    assert "cleartext: false" in capacitor
    assert "allowMixedContent: false" in capacitor
    assert "loggingBehavior: 'production'" in capacitor
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert 'android:allowBackup="false"' in manifest
    assert "10.0.2.2" not in capacitor


def test_capacitor_runtime_is_pinned_to_patched_release() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    assert package["dependencies"]["@capacitor/android"] == "8.5.3"
    assert package["dependencies"]["@capacitor/core"] == "8.5.3"
    assert package["devDependencies"]["@capacitor/cli"] == "8.5.3"


def test_mobile_origin_and_idempotency_header_are_allowed_by_fastapi() -> None:
    config = (ROOT / "backend/app/config.py").read_text(encoding="utf-8")
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")

    assert "https://localhost" in config
    assert '"Idempotency-Key"' in main
    assert 'allow_methods=["GET", "POST", "DELETE"]' in main


def test_android_build_refuses_insecure_or_misconfigured_dependencies() -> None:
    build_script = (ROOT / "scripts/build-android-apk.mjs").read_text(encoding="utf-8")

    assert 'backendUrl.protocol !== "https:"' in build_script
    assert 'supabaseUrl.protocol !== "https:"' in build_script
    assert "VITE_SUPABASE_ANON_KEY is required" in build_script
    assert 'Origin: "https://localhost"' in build_script
    assert 'body?.llm_provider !== "gigachat"' in build_script
    assert "body?.agent_infrastructure_test_mode !== false" in build_script
    assert '"Access-Control-Request-Headers": [' in build_script
    for required_header in (
        '"authorization"',
        '"content-type"',
        '"idempotency-key"',
        '...Object.keys(ngrokHeaders)',
    ):
        assert required_header in build_script


def test_android_release_build_requires_signing_and_verifies_artifacts() -> None:
    build_script = (ROOT / "scripts/build-android-apk.mjs").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/android-release.yml").read_text(encoding="utf-8")

    assert "ATHENA_ANDROID_KEYSTORE_FILE" in build_script
    assert "ATHENA_VERSION_CODE" in build_script
    assert "lintRelease assembleRelease bundleRelease" in build_script
    assert "npm audit --omit=dev --audit-level=high" in workflow
    assert '"$apksigner" verify' in workflow
    assert "jarsigner -verify" in workflow
