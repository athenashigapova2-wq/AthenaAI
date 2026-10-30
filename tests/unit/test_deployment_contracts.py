import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backend_docker_image_is_cpu_only() -> None:
    dockerfile = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "image: athenaai-backend:cpu" in compose
    assert "https://download.pytorch.org/whl/cpu" in dockerfile
    assert 'CUDA_VISIBLE_DEVICES=""' in dockerfile
    assert "assert '+cpu' in torch.__version__" in dockerfile
    assert "assert not torch.cuda.is_available()" in dockerfile
    assert "/whl/cu" not in dockerfile


def test_vercel_uses_validated_spa_build() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    validator = (ROOT / "scripts/validate-web-env.mjs").read_text(encoding="utf-8")

    assert config["framework"] == "vite"
    assert config["buildCommand"] == "npm run build:web"
    assert config["outputDirectory"] == "dist"
    assert config["rewrites"] == [{"source": "/(.*)", "destination": "/index.html"}]
    assert "validate-web-env.mjs" in package["scripts"]["build:web"]
    for variable in ("VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY", "VITE_AGENT_API_URL"):
        assert variable in validator
    assert "must use HTTPS" in validator
    assert "must not point to localhost" in validator
