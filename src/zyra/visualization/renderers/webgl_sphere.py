# SPDX-License-Identifier: Apache-2.0
"""WebGL/Three.js based globe renderer."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

from .base import InteractiveBundle, InteractiveRenderer
from .registry import register


@register
class WebGLSphereRenderer(InteractiveRenderer):
    slug = "webgl-sphere"
    description = "Three.js based sphere renderer that emits a standalone bundle."

    def build(self, *, output_dir: Path) -> InteractiveBundle:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        assets_dir = output_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        index_html = output_dir / "index.html"
        script_path = assets_dir / "sphere.js"
        config_path = assets_dir / "config.json"

        asset_overrides, asset_files = self._stage_assets(assets_dir)

        config = self._sanitized_config(overrides=asset_overrides)
        config_json = json.dumps(config, indent=2)
        config_path.write_text(config_json + "\n", encoding="utf-8")

        index_html.write_text(self._render_index_html(config), encoding="utf-8")
        script_path.write_text(self._render_script(), encoding="utf-8")

        return InteractiveBundle(
            output_dir=output_dir,
            index_html=index_html,
            assets=(script_path, config_path, *asset_files),
        )

    def _stage_assets(
        self, assets_dir: Path
    ) -> tuple[dict[str, object], tuple[Path, ...]]:
        """Copy optional assets (textures, legends) into bundle."""

        staged: list[Path] = []
        overrides: dict[str, object] = {}

        textures_dir = assets_dir / "textures"
        data_dir = assets_dir / "data"
        texture = self._options.get("texture")
        if texture:
            staged.append(
                self._copy_asset(Path(texture), textures_dir, overrides, "texture")
            )

        frame_entries = self._collect_frames()
        if frame_entries:
            frames_dir = textures_dir
            frames_dir.mkdir(parents=True, exist_ok=True)
            staged_paths = []
            manifest: list[dict[str, object]] = []
            for entry in frame_entries:
                src = Path(entry["path"]).expanduser()
                if not src.is_file():
                    msg = f"Frame file not found: {src}"
                    raise FileNotFoundError(msg)
                dest = frames_dir / src.name
                if src.resolve() != dest.resolve():
                    dest.write_bytes(src.read_bytes())
                staged_paths.append(dest)
                manifest.append(
                    {
                        "path": f"assets/textures/{src.name}",
                        "timestamp": entry.get("timestamp"),
                    }
                )
            overrides["frames"] = manifest
            overrides.setdefault("texture", manifest[0]["path"])
            staged.extend(staged_paths)

        gradients_dir = assets_dir / "gradients"
        probe_gradient = self._options.get("probe_gradient")
        if probe_gradient:
            staged.append(
                self._copy_asset(
                    Path(probe_gradient), gradients_dir, overrides, "probe_gradient"
                )
            )

        probe_lut = self._options.get("probe_lut")
        if probe_lut:
            staged.append(
                self._copy_asset(Path(probe_lut), gradients_dir, overrides, "probe_lut")
            )

        probe_data = self._options.get("probe_data")
        if probe_data:
            staged.append(
                self._copy_asset(Path(probe_data), data_dir, overrides, "probe_data")
            )

        return overrides, tuple(staged)

    def _collect_frames(self) -> list[dict[str, object]]:
        pattern = self._options.get("texture_pattern")
        frame_list = self._options.get("frame_list")

        entries: list[dict[str, object]] = []
        if pattern:
            base = Path(pattern)
            for path in sorted(base.parent.glob(base.name)):
                entries.append({"path": str(path)})

        if frame_list:
            frame_file = Path(frame_list)
            if not frame_file.is_file():
                msg = f"Frame list file not found: {frame_file}"
                raise FileNotFoundError(msg)
            for line in frame_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                payload = {"path": parts[0]}
                if len(parts) > 1:
                    payload["timestamp"] = " ".join(parts[1:])
                entries.append(payload)

        seen = set()
        unique_entries = []
        for entry in entries:
            key = (entry["path"], entry.get("timestamp"))
            if key in seen:
                continue
            seen.add(key)
            unique_entries.append(entry)
        return unique_entries

    def _copy_asset(
        self,
        source: Path,
        target_dir: Path,
        overrides: dict[str, object],
        key: str,
    ) -> Path:
        source = source.expanduser()
        if not source.is_file():
            msg = f"{key.capitalize()} file not found: {source}"
            raise FileNotFoundError(msg)
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / source.name
        if source.resolve() != dest.resolve():
            dest.write_bytes(source.read_bytes())
        rel_dir_map = {
            "probe_gradient": "gradients",
            "probe_lut": "gradients",
            "probe_data": "data",
        }
        rel_dir = rel_dir_map.get(key, "textures")
        overrides[key] = f"assets/{rel_dir}/{source.name}"
        return dest

    def _sanitized_config(
        self, *, overrides: dict[str, object] | None = None
    ) -> dict[str, object]:
        """Return config suitable for embedding (no sensitive values)."""

        secrets = {
            "credentials",
            "auth",
            "credential_file",
            "texture",
            "texture_pattern",
            "frame_list",
            "frame_cache",
            "probe_gradient",
            "probe_lut",
            "probe_data",
        }
        filtered = {
            key: value
            for key, value in self._options.items()
            if key not in secrets and value is not None
        }
        filtered.setdefault("width", None)
        filtered.setdefault("height", None)
        filtered.setdefault("animate", "none")
        filtered.setdefault("probe_enabled", True)
        if overrides:
            filtered.update(overrides)
        return filtered

    def _render_index_html(self, config: dict[str, object]) -> str:
        """Return the HTML entry point for the bundle."""

        config_json = json.dumps(config, indent=2)
        return (
            dedent(
                f"""
            <!DOCTYPE html>
            <html lang=\"en\">
              <head>
                <meta charset=\"utf-8\" />
                <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
                <title>Zyra WebGL Globe</title>
                <style>
                  body, html {{ margin: 0; padding: 0; background: #0f1114; color: #f5f7fa; font-family: system-ui, sans-serif; }}
                  #zyra-globe {{ width: 100vw; height: 100vh; display: block; }}
                  #zyra-overlay {{ position: absolute; top: 16px; left: 16px; background: rgba(0, 0, 0, 0.55); padding: 12px 16px; border-radius: 8px; max-width: 320px; }}
                  #zyra-overlay code {{ font-size: 0.85rem; }}
                  #zyra-probe {{ margin-top: 10px; font-size: 0.85rem; line-height: 1.35; }}
                  #zyra-probe .probe-header {{ font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; font-size: 0.8rem; }}
                  #zyra-probe .probe-line {{ display: flex; align-items: center; gap: 6px; white-space: nowrap; }}
                  #zyra-probe .probe-label {{ min-width: 68px; color: rgba(245, 247, 250, 0.75); }}
                  #zyra-probe .probe-swatch {{ width: 14px; height: 14px; border: 1px solid rgba(245, 247, 250, 0.65); border-radius: 2px; background: transparent; display: inline-block; box-sizing: border-box; }}
                </style>
              </head>
              <body>
                <canvas id=\"zyra-globe\"></canvas>
                <div id=\"zyra-overlay\">
                  <strong>Zyra WebGL Sphere (beta)</strong>
                  <p>Renderer target: <code>{self.slug}</code></p>
                  <div id=\"zyra-probe\">
                    <div class=\"probe-header\">Probe</div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Latitude</span><span data-probe-lat>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Longitude</span><span data-probe-lon>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Frame</span><span data-probe-frame>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Color</span><span class=\"probe-swatch\" data-probe-swatch></span><code data-probe-hex>—</code></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Value</span><span data-probe-value>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Units</span><span data-probe-units>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Gradient</span><span data-probe-gradient>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">LUT</span><span data-probe-lut>—</span></div>
                  </div>
                </div>
                <script>
                  window.ZYRA_GLOBE_CONFIG = {config_json};
                </script>
                <script type=\"module\" src=\"assets/sphere.js\"></script>
              </body>
            </html>
            """
            ).strip()
            + "\n"
        )

    def _render_script(self) -> str:
        """Return the JavaScript module that boots the globe."""

        return (
            dedent(
                """
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.161.0/build/three.module.js";

(async function bootstrap() {
  const config = window.ZYRA_GLOBE_CONFIG || {};
  const canvas = document.getElementById("zyra-globe");
  if (!canvas) {
    console.warn("Zyra globe canvas element not found");
    return;
  }

  if (config.probe_enabled) {
    canvas.style.cursor = "crosshair";
  }

  const probeContainer = document.getElementById("zyra-probe");
  const probeLatEl = document.querySelector("[data-probe-lat]");
  const probeLonEl = document.querySelector("[data-probe-lon]");
  const probeFrameEl = document.querySelector("[data-probe-frame]");
  const probeHexEl = document.querySelector("[data-probe-hex]");
  const probeSwatchEl = document.querySelector("[data-probe-swatch]");
  const probeGradientEl = document.querySelector("[data-probe-gradient]");
  const probeLutEl = document.querySelector("[data-probe-lut]");
  const probeValueEl = document.querySelector("[data-probe-value]");
  const probeUnitsEl = document.querySelector("[data-probe-units]");

  if (!config.probe_enabled && probeContainer) {
    probeContainer.style.opacity = "0.6";
  }

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x050608);

  const camera = new THREE.PerspectiveCamera(
    45,
    window.innerWidth / window.innerHeight,
    0.1,
    1000,
  );
  camera.position.set(0, 0, 3);

  const samplerCache = new Map();
  const textureCache = new Map();

  async function loadImageSampler(url) {
    try {
      const image = new Image();
      image.src = url;
      if (!url.startsWith("data:")) {
        image.crossOrigin = "anonymous";
      }
      await image.decode();
      const canvasSampler = document.createElement("canvas");
      canvasSampler.width = image.width;
      canvasSampler.height = image.height;
      const ctx = canvasSampler.getContext("2d");
      ctx.drawImage(image, 0, 0);
      const imageData = ctx.getImageData(0, 0, canvasSampler.width, canvasSampler.height);
      return {
        width: canvasSampler.width,
        height: canvasSampler.height,
        data: imageData.data,
      };
    } catch (error) {
      console.warn("Failed to load sampler image", url, error);
      return null;
    }
  }

  async function fetchText(url) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Fetch failed: ${response.status}`);
    }
    return response.text();
  }

  async function loadJson(url) {
    try {
      const text = await fetchText(url);
      return JSON.parse(text);
    } catch (error) {
      console.warn("Failed to load JSON", url, error);
      return null;
    }
  }

  function parseCsvDataset(text) {
    const lines = text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (!lines.length) {
      return null;
    }
    const headers = lines[0]
      .split(",")
      .map((h) => h.trim().toLowerCase());
    const latIdx = headers.findIndex((h) => h === "lat" || h === "latitude");
    const lonIdx = headers.findIndex((h) => h === "lon" || h === "lng" || h === "long" || h === "longitude");
    const valueIdx = headers.findIndex((h) => h === "value" || h === "val" || h === "data");
    const unitsIdx = headers.findIndex((h) => h === "units" || h === "unit");
    if (latIdx === -1 || lonIdx === -1 || valueIdx === -1) {
      return null;
    }
    const points = [];
    for (let i = 1; i < lines.length; i += 1) {
      const parts = lines[i].split(",").map((p) => p.trim());
      if (parts.length < headers.length) {
        continue;
      }
      const lat = Number(parts[latIdx]);
      const lon = Number(parts[lonIdx]);
      const value = Number(parts[valueIdx]);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(value)) {
        continue;
      }
      const entry = { lat, lon, value };
      if (unitsIdx !== -1 && parts[unitsIdx]) {
        entry.units = parts[unitsIdx];
      }
      points.push(entry);
    }
    return points.length ? { points } : null;
  }

  function normalizeProbeArray(raw) {
    if (!Array.isArray(raw)) {
      return null;
    }
    const points = [];
    for (const entry of raw) {
      if (typeof entry !== "object" || entry == null) {
        continue;
      }
      const lat = Number(entry.lat ?? entry.latitude);
      const lon = Number(entry.lon ?? entry.lng ?? entry.long ?? entry.longitude);
      const value = Number(entry.value ?? entry.val ?? entry.data);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(value)) {
        continue;
      }
      points.push({
        lat,
        lon,
        value,
        units: entry.units ?? entry.unit ?? null,
      });
    }
    return points.length ? { points } : null;
  }

  async function loadProbeDataset(url) {
    try {
      const text = await fetchText(url);
      try {
        const parsed = JSON.parse(text);
        const normalized = normalizeProbeArray(parsed);
        if (normalized) {
          return normalized;
        }
      } catch (jsonError) {
        // fall through to CSV parser
      }
      const csv = parseCsvDataset(text);
      if (csv) {
        return csv;
      }
      console.warn("Unsupported probe dataset format", url);
    } catch (error) {
      console.warn("Failed to load probe dataset", url, error);
    }
    return null;
  }

  function nearestProbe(lat, lon, dataset) {
    if (!dataset || !dataset.points || !dataset.points.length) {
      return null;
    }
    const latRad = THREE.MathUtils.degToRad(lat);
    const lonRad = THREE.MathUtils.degToRad(lon);
    let best = null;
    let bestScore = Infinity;
    for (const point of dataset.points) {
      const pLat = THREE.MathUtils.degToRad(point.lat);
      const pLon = THREE.MathUtils.degToRad(point.lon);
      const dLat = latRad - pLat;
      const dLon = lonRad - pLon;
      const sinLat = Math.sin(dLat / 2);
      const sinLon = Math.sin(dLon / 2);
      const a =
        sinLat * sinLat +
        Math.cos(latRad) * Math.cos(pLat) * sinLon * sinLon;
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      if (c < bestScore) {
        bestScore = c;
        best = point;
      }
    }
    return best;
  }

  const gradientSampler = config.probe_gradient
    ? await loadImageSampler(config.probe_gradient)
    : null;
  const lutTable = config.probe_lut ? await loadJson(config.probe_lut) : null;
  const probeDataset = config.probe_data
    ? await loadProbeDataset(config.probe_data)
    : null;

  const loader = new THREE.TextureLoader();
  const frames = Array.isArray(config.frames) ? config.frames : null;

  const sphereGeometry = new THREE.SphereGeometry(1, 64, 64);
  const sphereMaterial = new THREE.MeshStandardMaterial({
    color: 0x1f6feb,
    wireframe: !config.texture && !(frames && frames.length),
  });

  let currentTextureUri = null;
  let currentFrameMeta = frames && frames.length ? frames[0] : null;
  let currentFrameIndex = 0;

  function prepareSampler(texture, uri) {
    if (!texture || !texture.image) {
      return;
    }
    const image = texture.image;
    const width = image.width;
    const height = image.height;
    if (!width || !height) {
      return;
    }
    const canvasSampler = document.createElement("canvas");
    canvasSampler.width = width;
    canvasSampler.height = height;
    const ctx = canvasSampler.getContext("2d");
    ctx.drawImage(image, 0, 0);
    const imageData = ctx.getImageData(0, 0, width, height);
    samplerCache.set(uri, {
      width,
      height,
      data: imageData.data,
    });
  }

  function ensureSampler(uri) {
    if (!uri || samplerCache.has(uri)) {
      return;
    }
    const cachedTexture = textureCache.get(uri);
    if (cachedTexture) {
      prepareSampler(cachedTexture, uri);
    }
  }

  function sampleTexture(uv) {
    const uri = currentTextureUri;
    if (!uri) {
      return null;
    }
    ensureSampler(uri);
    const sampler = samplerCache.get(uri);
    if (!sampler) {
      return null;
    }
    const { width, height, data } = sampler;
    const x = Math.min(width - 1, Math.max(0, Math.round(uv.x * (width - 1))));
    const y = Math.min(height - 1, Math.max(0, Math.round((1 - uv.y) * (height - 1))));
    const idx = (y * width + x) * 4;
    return {
      r: data[idx],
      g: data[idx + 1],
      b: data[idx + 2],
      a: data[idx + 3],
    };
  }

  function formatHex(color) {
    const toHex = (value) => value.toString(16).padStart(2, "0");
    return `#${toHex(color.r)}${toHex(color.g)}${toHex(color.b)}`.toUpperCase();
  }

  function formatValue(value) {
    if (!Number.isFinite(value)) {
      return "—";
    }
    if (Math.abs(value) >= 1000 || Math.abs(value) < 0.01) {
      return value.toExponential(2);
    }
    return value.toFixed(2);
  }

  function mapGradient(color) {
    if (!gradientSampler) {
      return null;
    }
    const { width, height, data } = gradientSampler;
    if (!width || !height) {
      return null;
    }
    const row = Math.floor(height / 2);
    let bestIdx = 0;
    let bestScore = Infinity;
    for (let x = 0; x < width; x += 1) {
      const idx = (row * width + x) * 4;
      const dr = data[idx] - color.r;
      const dg = data[idx + 1] - color.g;
      const db = data[idx + 2] - color.b;
      const score = dr * dr + dg * dg + db * db;
      if (score < bestScore) {
        bestScore = score;
        bestIdx = x;
      }
    }
    return width > 1 ? bestIdx / (width - 1) : 0;
  }

  function lookupLut(hex) {
    if (!lutTable || !hex) {
      return null;
    }
    if (Array.isArray(lutTable)) {
      const entry = lutTable.find((item) => {
        if (typeof item !== "object" || !item) {
          return false;
        }
        const colorKey = item.color || item.hex || item.colour;
        return typeof colorKey === "string" && colorKey.toUpperCase() === hex;
      });
      if (entry && Object.prototype.hasOwnProperty.call(entry, "value")) {
        return entry.value;
      }
      if (entry && Object.prototype.hasOwnProperty.call(entry, "label")) {
        return entry.label;
      }
      return entry ?? null;
    }
    if (typeof lutTable === "object") {
      return (
        lutTable[hex] ??
        lutTable[hex.toLowerCase?.() || ""] ??
        null
      );
    }
    return null;
  }

  function applyTexture(uri, texture, frameMeta) {
    texture.colorSpace = THREE.SRGBColorSpace;
    textureCache.set(uri, texture);
    sphereMaterial.map = texture;
    sphereMaterial.wireframe = false;
    sphereMaterial.needsUpdate = true;
    prepareSampler(texture, uri);
    if (frameMeta) {
      currentFrameMeta = frameMeta;
    }
  }

  function resolveTexture(uri, frameMeta) {
    if (!uri) {
      return;
    }
    currentTextureUri = uri;
    currentFrameMeta = frameMeta || currentFrameMeta;
    if (textureCache.has(uri)) {
      applyTexture(uri, textureCache.get(uri), frameMeta || currentFrameMeta);
      return;
    }
    loader.load(
      uri,
      (texture) => applyTexture(uri, texture, frameMeta || currentFrameMeta),
      undefined,
      (error) => console.warn("Failed to load texture", uri, error),
    );
  }

  const sphere = new THREE.Mesh(sphereGeometry, sphereMaterial);
  scene.add(sphere);

  const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
  scene.add(ambientLight);

  const directionalLight = new THREE.DirectionalLight(0xffffff, 0.6);
  directionalLight.position.set(5, 5, 5);
  scene.add(directionalLight);

  function resizeRenderer() {
    const widthValue = config.width || window.innerWidth;
    const heightValue = config.height || window.innerHeight;
    renderer.setSize(widthValue, heightValue, false);
    camera.aspect = widthValue / heightValue;
    camera.updateProjectionMatrix();
  }

  window.addEventListener("resize", resizeRenderer);
  resizeRenderer();

  const initialFrame = frames && frames.length ? frames[0] : null;
  if (initialFrame) {
    resolveTexture(initialFrame.path, initialFrame);
  } else if (config.texture) {
    resolveTexture(config.texture, null);
  }

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();

  function updateProbeDisplay(payload) {
    if (!probeLatEl || !probeLonEl) {
      return;
    }
    if (!payload) {
      probeLatEl.textContent = "—";
      probeLonEl.textContent = "—";
      if (probeFrameEl) probeFrameEl.textContent = "—";
      if (probeHexEl) probeHexEl.textContent = "—";
      if (probeGradientEl) probeGradientEl.textContent = "—";
      if (probeLutEl) probeLutEl.textContent = "—";
      if (probeValueEl) probeValueEl.textContent = "—";
      if (probeUnitsEl) probeUnitsEl.textContent = "—";
      if (probeSwatchEl) {
        probeSwatchEl.style.background = "transparent";
        probeSwatchEl.style.borderColor = "rgba(245, 247, 250, 0.65)";
      }
      return;
    }
    probeLatEl.textContent = `${payload.lat.toFixed(2)}°`;
    probeLonEl.textContent = `${payload.lon.toFixed(2)}°`;
    if (probeFrameEl) {
      if (payload.frameTimestamp) {
        probeFrameEl.textContent = payload.frameTimestamp;
      } else if (payload.frameIndex != null) {
        probeFrameEl.textContent = `#${payload.frameIndex + 1}`;
      } else {
        probeFrameEl.textContent = "—";
      }
    }
    if (probeHexEl) {
      probeHexEl.textContent = payload.hex || "—";
    }
    if (probeSwatchEl) {
      if (payload.hex) {
        probeSwatchEl.style.background = payload.hex;
        probeSwatchEl.style.borderColor = payload.hex;
      } else {
        probeSwatchEl.style.background = "transparent";
        probeSwatchEl.style.borderColor = "rgba(245, 247, 250, 0.65)";
      }
    }
    if (probeGradientEl) {
      probeGradientEl.textContent =
        payload.gradient != null ? `${(payload.gradient * 100).toFixed(1)}%` : "—";
    }
    if (probeLutEl) {
      probeLutEl.textContent = payload.lutValue != null ? String(payload.lutValue) : "—";
    }
    if (probeValueEl) {
      probeValueEl.textContent =
        payload.dataValue != null ? formatValue(payload.dataValue) : "—";
    }
    if (probeUnitsEl) {
      probeUnitsEl.textContent = payload.dataUnits ?? "—";
    }
  }

  function clearProbe() {
    updateProbeDisplay(null);
  }

  function handlePointer(event) {
    if (!config.probe_enabled) {
      return;
    }
    const rect = canvas.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObject(sphere);
    if (!hits.length) {
      clearProbe();
      return;
    }
    const hit = hits[0];
    const point = hit.point.clone().normalize();
    const lat = THREE.MathUtils.radToDeg(Math.asin(point.y));
    let lon = THREE.MathUtils.radToDeg(Math.atan2(point.x, point.z));
    if (lon > 180) {
      lon -= 360;
    }
    if (lon < -180) {
      lon += 360;
    }

    let hex = null;
    let gradientValue = null;
    let lutValue = null;
    let dataValue = null;
    let dataUnits = null;

    if (hit.uv) {
      const color = sampleTexture(hit.uv);
      if (color) {
        hex = formatHex(color);
        const gradientRatio = mapGradient(color);
        gradientValue = gradientRatio != null ? gradientRatio : null;
        lutValue = lookupLut(hex);
      }
    }

    if (probeDataset) {
      const nearest = nearestProbe(lat, lon, probeDataset);
      if (nearest) {
        dataValue = nearest.value;
        dataUnits = nearest.units ?? config.probe_units ?? null;
      }
    }

    updateProbeDisplay({
      lat,
      lon,
      hex,
      gradient: gradientValue,
      lutValue,
      dataValue,
      dataUnits,
      frameIndex: frames && frames.length ? currentFrameIndex : null,
      frameTimestamp:
        currentFrameMeta && currentFrameMeta.timestamp
          ? currentFrameMeta.timestamp
          : null,
    });
  }

  if (config.probe_enabled) {
    canvas.addEventListener("pointermove", handlePointer);
    canvas.addEventListener("pointerleave", () => {
      clearProbe();
    });
    clearProbe();
  }

  let lastTime = 0;
  let frameTime = 0;
  const frameDuration = Number(config.frame_duration) || 0.25;

  function render(time) {
    const delta = (time - lastTime) / 1000;
    lastTime = time;
    sphere.rotation.y += delta * 0.25;
    if (
      config.animate === "time" &&
      frames &&
      frames.length > 1
    ) {
      frameTime += delta;
      if (frameTime >= frameDuration) {
        frameTime = 0;
        currentFrameIndex = (currentFrameIndex + 1) % frames.length;
        const frameMeta = frames[currentFrameIndex];
        resolveTexture(frameMeta.path, frameMeta);
      }
    }
    renderer.render(scene, camera);
    requestAnimationFrame(render);
  }

  requestAnimationFrame(render);
})().catch((error) => {
  console.error("Zyra globe bootstrap failed", error);
});

"""
            ).strip()
            + "\n"
        )
