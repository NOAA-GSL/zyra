# SPDX-License-Identifier: Apache-2.0
"""CesiumJS-based interactive globe renderer.

The generated bundle references Cesium assets via jsDelivr CDN. Future
iterations can add an option to vendor or pin a local copy if offline support
is required.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

from .base import InteractiveBundle, InteractiveRenderer
from .registry import register


@register
class CesiumGlobeRenderer(InteractiveRenderer):
    slug = "cesium-globe"
    description = "CesiumJS globe renderer that emits a standalone bundle."

    def build(self, *, output_dir: Path) -> InteractiveBundle:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        assets_dir = output_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        index_html = output_dir / "index.html"
        script_path = assets_dir / "cesium.js"
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
        """Copy optional assets (gradients, LUTs, textures) into bundle."""

        staged: list[Path] = []
        overrides: dict[str, object] = {}

        gradients_dir = assets_dir / "gradients"
        textures_dir = assets_dir / "textures"
        data_dir = assets_dir / "data"

        texture = self._options.get("texture")
        if texture:
            staged.append(
                self._copy_asset(Path(texture), textures_dir, overrides, "texture")
            )

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

        legend_texture = self._options.get("legend_texture")
        if legend_texture:
            staged.append(
                self._copy_asset(
                    Path(legend_texture), textures_dir, overrides, "legend_texture"
                )
            )

        return overrides, tuple(staged)

    def _copy_asset(
        self,
        source: Path,
        target_dir: Path,
        overrides: dict[str, object],
        key: str,
    ) -> Path:
        source = source.expanduser()
        if not source.is_file():
            msg = f"{key.replace('_', ' ').capitalize()} file not found: {source}"
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
        """Return a Cesium config with sensitive keys removed."""

        secrets = {
            "credentials",
            "auth",
            "credential_file",
            "cesium_ion_token",
            "texture",
            "probe_gradient",
            "probe_lut",
            "probe_data",
            "legend_texture",
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
        config_json = json.dumps(config, indent=2)
        return (
            dedent(
                f"""
            <!DOCTYPE html>
            <html lang=\"en\">
              <head>
                <meta charset=\"utf-8\" />
                <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
                <title>Zyra Cesium Globe</title>
                <link
                  rel=\"stylesheet\"
                  href=\"https://cdn.jsdelivr.net/npm/cesium@1.114.0/Build/Cesium/Widgets/widgets.css\"
                />
                <style>
                  html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #0b0d11; color: #f5f7fa; font-family: system-ui, sans-serif; }}
                  #zyra-cesium {{ width: 100%; height: 100%; display: block; position: relative; }}
                  #zyra-overlay {{ position: absolute; top: 16px; left: 16px; background: rgba(0, 0, 0, 0.55); padding: 12px 16px; border-radius: 8px; max-width: 280px; z-index: 100; }}
                  #zyra-overlay code {{ font-size: 0.85rem; }}
                  #zyra-probe {{ margin-top: 10px; font-size: 0.85rem; line-height: 1.35; }}
                  #zyra-probe .probe-header {{ font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; font-size: 0.8rem; }}
                  #zyra-probe .probe-line {{ display: flex; align-items: center; gap: 6px; white-space: nowrap; }}
                  #zyra-probe .probe-label {{ min-width: 68px; color: rgba(245, 247, 250, 0.75); }}
                </style>
              </head>
              <body>
                <div id=\"zyra-cesium\">
                  <div id=\"zyra-overlay\">
                    <strong>Zyra Cesium Globe (beta)</strong>
                    <p>Renderer target: <code>{self.slug}</code></p>
                  <div id=\"zyra-probe\">
                    <div class=\"probe-header\">Probe</div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Latitude</span><span data-probe-lat>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Longitude</span><span data-probe-lon>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Height</span><span data-probe-height>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Value</span><span data-probe-value>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Units</span><span data-probe-units>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">Gradient</span><span data-probe-gradient>—</span></div>
                    <div class=\"probe-line\"><span class=\"probe-label\">LUT</span><span data-probe-lut>—</span></div>
                  </div>
                </div>
                </div>
                <script>
                  window.ZYRA_GLOBE_CONFIG = {config_json};
                </script>
                <script src=\"https://cdn.jsdelivr.net/npm/cesium@1.114.0/Build/Cesium/Cesium.js\"></script>
                <script src=\"assets/cesium.js\"></script>
              </body>
            </html>
            """
            ).strip()
            + "\n"
        )

    def _render_script(self) -> str:
        return (
            dedent(
                """
(async function () {
  const config = window.ZYRA_GLOBE_CONFIG || {};
  const container = document.getElementById("zyra-cesium");
  const overlay = document.getElementById("zyra-overlay");

  if (!window.Cesium) {
    overlay.innerHTML = "<strong>Cesium failed to load.</strong>";
    return;
  }

  const latEl = document.querySelector("[data-probe-lat]");
  const lonEl = document.querySelector("[data-probe-lon]");
  const heightEl = document.querySelector("[data-probe-height]");
  const gradientEl = document.querySelector("[data-probe-gradient]");
  const lutEl = document.querySelector("[data-probe-lut]");
  const valueEl = document.querySelector("[data-probe-value]");
  const unitsEl = document.querySelector("[data-probe-units]");

  const width = config.width || window.innerWidth;
  const height = config.height || window.innerHeight;
  container.style.width = `${width}px`;
  container.style.height = `${height}px`;

  const animate = config.animate === "time";

  const viewer = new Cesium.Viewer(container, {
    animation: animate,
    timeline: animate,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    infoBox: false,
  });

  viewer.scene.globe.enableLighting = true;
  viewer.scene.skyAtmosphere.show = true;
  viewer.scene.skyBox = new Cesium.SkyBox({ show: true });

  viewer.imageryLayers.removeAll();
  viewer.imageryLayers.addImageryProvider(Cesium.createWorldImagery());

  const canvas = viewer.scene.canvas;
  if (config.probe_enabled) {
    canvas.style.cursor = "crosshair";
  }

  function labelFromPath(value) {
    if (!value || typeof value !== "string") {
      return "—";
    }
    const parts = value.split("/");
    return parts[parts.length - 1] || value;
  }

  if (gradientEl) gradientEl.textContent = labelFromPath(config.probe_gradient);
  if (lutEl) lutEl.textContent = labelFromPath(config.probe_lut);

  if (!config.probe_enabled && overlay) {
    overlay.style.opacity = "0.65";
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
      console.warn("Cesium probe: failed to load JSON", url, error);
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
      console.warn("Cesium probe: unsupported dataset format", url);
    } catch (error) {
      console.warn("Cesium probe: failed to load dataset", url, error);
    }
    return null;
  }

  function nearestProbe(lat, lon, dataset) {
    if (!dataset || !dataset.points || !dataset.points.length) {
      return null;
    }
    const latRad = Cesium.Math.toRadians(lat);
    const lonRad = Cesium.Math.toRadians(lon);
    let best = null;
    let bestScore = Infinity;
    for (const point of dataset.points) {
      const pLat = Cesium.Math.toRadians(point.lat);
      const pLon = Cesium.Math.toRadians(point.lon);
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

  function formatValue(value) {
    if (!Number.isFinite(value)) {
      return "—";
    }
    if (Math.abs(value) >= 1000 || Math.abs(value) < 0.01) {
      return value.toExponential(2);
    }
    return value.toFixed(2);
  }

  const probeDataset = config.probe_data
    ? await loadProbeDataset(config.probe_data)
    : null;

  const handler = new Cesium.ScreenSpaceEventHandler(canvas);
  const ellipsoid = viewer.scene.globe.ellipsoid;

  function updateProbeDisplay(payload) {
    if (!latEl || !lonEl) {
      return;
    }
    if (!payload) {
      latEl.textContent = "—";
      lonEl.textContent = "—";
      if (heightEl) heightEl.textContent = "—";
      if (valueEl) valueEl.textContent = "—";
      if (unitsEl) unitsEl.textContent = "—";
      return;
    }
    latEl.textContent = `${payload.lat.toFixed(2)}°`;
    lonEl.textContent = `${payload.lon.toFixed(2)}°`;
    if (heightEl) {
      if (Number.isFinite(payload.height)) {
        heightEl.textContent = `${payload.height.toFixed(0)} m`;
      } else {
        heightEl.textContent = "—";
      }
    }
    if (valueEl) {
      valueEl.textContent =
        payload.dataValue != null ? formatValue(payload.dataValue) : "—";
    }
    if (unitsEl) {
      unitsEl.textContent = payload.dataUnits ?? "—";
    }
  }

  function clearProbe() {
    updateProbeDisplay(null);
  }

  if (config.probe_enabled) {
    handler.setInputAction((movement) => {
      const cartesian = viewer.camera.pickEllipsoid(
        movement.endPosition,
        ellipsoid,
      );
      if (!Cesium.defined(cartesian)) {
        clearProbe();
        return;
      }
      const cartographic = ellipsoid.cartesianToCartographic(cartesian);
      const lat = Cesium.Math.toDegrees(cartographic.latitude);
      let lon = Cesium.Math.toDegrees(cartographic.longitude);
      if (lon > 180) lon -= 360;
      if (lon < -180) lon += 360;
      let heightMeters = viewer.scene.globe.getHeight(cartographic);
      if (!Number.isFinite(heightMeters)) {
        heightMeters = cartographic.height;
      }

      let dataValue = null;
      let dataUnits = null;
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
        height: heightMeters,
        dataValue,
        dataUnits,
      });
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    canvas.addEventListener("mouseleave", clearProbe);
    clearProbe();
  }

  window.addEventListener("resize", () => {
    const w = config.width || window.innerWidth;
    const h = config.height || window.innerHeight;
    container.style.width = `${w}px`;
    container.style.height = `${h}px`;
    viewer.resize();
  });
})();

"""
            ).strip()
            + "\n"
        )
