from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_android_release_surface_requires_secure_transport() -> None:
    capacitor = (ROOT / "capacitor.config.ts").read_text(encoding="utf-8")
    manifest = (
        ROOT / "android/app/src/main/AndroidManifest.xml"
    ).read_text(encoding="utf-8")

    assert "androidScheme: 'https'" in capacitor
    assert "cleartext: false" in capacitor
    assert "allowMixedContent: false" in capacitor
    assert "loggingBehavior: 'production'" in capacitor
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert "10.0.2.2" not in capacitor


def test_mobile_origin_and_idempotency_header_are_allowed_by_fastapi() -> None:
    config = (ROOT / "backend/app/config.py").read_text(encoding="utf-8")
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")

    assert "https://localhost" in config
    assert '"Idempotency-Key"' in main


def test_android_build_refuses_insecure_or_misconfigured_dependencies() -> None:
    build_script = (
        ROOT / "scripts/build-android-apk.mjs"
    ).read_text(encoding="utf-8")

    assert 'backendUrl.protocol !== "https:"' in build_script
    assert 'supabaseUrl.protocol !== "https:"' in build_script
    assert 'VITE_SUPABASE_ANON_KEY is required' in build_script
    assert 'Origin: "https://localhost"' in build_script
    assert (
        '"Access-Control-Request-Headers": '
        '"authorization,content-type,idempotency-key"'
    ) in build_script
