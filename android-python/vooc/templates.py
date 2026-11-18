"""Templates: reusable visualizer looks (.viz files = JSON, .vzb = bundle with assets).

A template stores every layer of the ProjectModel (order, visibility and all
property values) but not the playlist, so one look can be reused for any
track. File format::

    {"format": "vooc-viz", "version": 2, "name": "...", "meta": {...}, "thumbnail": "<base64 png>",
     "layers": [LayerModel.to_dict(), ...]}

Version 1 files (no meta / thumbnail) are migrated on load. A ``.vzb`` bundle is
``b"VZB1" + zlib(json({"template": ..., "assets": {key: base64}}))``: every image /
font / file referenced by a layer is embedded so the look works on another phone.

Built-in templates are generated from the default project with overrides, so
they always match the current schema.
"""
import base64
import hashlib
import json
import os
import re
import struct
import time
import uuid
import zlib
import zipfile
import io
from pathlib import Path

from .model import DEFAULT_LAYER_ORDER, LayerModel, ProjectModel

FORMAT = "vooc-viz"
VERSION = 2
APP_VERSION = "1.0"
BUNDLE_MAGIC = b"VZB1"
AVP_FORMAT = "vooc-avp"
AVP_VERSION = 1
MAX_AVP_ENTRIES = 512
MAX_AVP_TOTAL_BYTES = 64 * 1024 * 1024
MAX_ASSET_BYTES = 12 * 1024 * 1024        # per asset, keeps bundles shareable
ASSET_TYPES = ("image", "font", "file")
KEEP_ON_APPLY = ("AUDIOPROVIDER",)       # device audio routing is not part of a look


class _LazyLayerMap(dict):
    """Create template layers only when a built-in preset actually references them."""
    def __init__(self, project):
        super().__init__((layer.module, layer) for layer in project.layers)
        self.project = project

    def __missing__(self, module):
        layer = self.project.layer(module)
        self[module] = layer
        return layer


def _fx_on(layers, module, **values):
    layer = layers[module]
    layer.set("General/Layer/Visible", True)
    for k, v in values.items():
        layer.set(k, v)


def _builtin(name):
    p = ProjectModel()
    L = _LazyLayerMap(p)
    if name == "Circle Classic":
        # The default look now creates only its actual visual element.
        b = L["BARS"]
        b.set("General/Layer/Visible", True)
        b.set("Bars Setup/Bars/Shape Path", "Circle")
    elif name == "Linear Spectrum":
        b = L["BARS"]
        b.set("Bars Setup/Bars/Shape Path", "HorizontalLine")
        b.set("Bars Setup/Bars/Path Size", 0.24)
        b.set("Bars Setup/Bars/Bar Count", 96)
        b.set("Bars Setup/Bars/Max Height Scale", 0.42)
        b.set("General/Position/Position Y", 0.30)
        b.set("Segment 1/Segment 1/Mirror", True)
        L["IMAGE"].set("General/Layer/Visible", False)
        L["TEXT"].set("General/Position/Position Y", 0.80)
        L["PARTICLES"].set("Overall Settings/Emitter/Spawn Area", "Rectangle")
        _fx_on(L, "BLUREFFECT")
    elif name == "Mirror Wave":
        b = L["BARS"]
        b.set("Bars Setup/Bars/Shape Path", "WaveformPath")
        b.set("Bars Setup/Bars/Path Size", 0.24)
        b.set("Bars Setup/Bars/Bar Count", 128)
        b.set("Bars Setup/Bars/Bar Width", 0.5)
        L["IMAGE"].set("General/Layer/Visible", False)
        _fx_on(L, "MIRROREREFFECT", **{"Appearance/Mirror/Mirror Mode": "Vertical"})
        _fx_on(L, "BLUREFFECT")
    elif name == "Neon Kaleido":
        b = L["BARS"]
        b.set("Bars Setup/Bars/Shape Path", "Star")
        b.set("Bars Setup/Bars/Bar Count", 120)
        L["COMPOSITION"].set("General/Measure Engine/Measure Rot", "TotalTimeWhenPlaying")
        L["COMPOSITION"].set("General/Measure Engine/Rot Amount (A)", 0.05)
        _fx_on(L, "BLUREFFECT")
        _fx_on(L, "RGBSPLITEFFECT")
        _shader(L["CUSTOMSHADER"], "Kaleidoscope")
    elif name == "Zoom Pulse":
        b = L["BARS"]
        b.set("Bars Setup/Bars/Bar Count", 90)
        b.set("Bars Setup/Bars/Max Height Scale", 0.3)
        _fx_on(L, "BLUREFFECT")
        _shader(L["CUSTOMSHADER"], "Zoom Blur")
    elif name == "Retro 3D Box":
        b = L["BARS"]
        b.set("Bars Setup/Bars/Shape Path", "Square")
        b.set("Bars Setup/Bars/Bar Count", 96)
        L["IMAGE"].set("Image Source/Source/Shape", "Square")
        _shader(L["CUSTOMSHADER"], "3D Box")
    elif name == "Twirl Galaxy":
        L["PARTICLES"].set("Overall Settings/Emitter/Count Limit", 900)
        L["PARTICLES"].set("Overall Settings/Emitter/Force Field", "Vortex")
        L["BARS"].set("Bars Setup/Bars/Shape Path", "SidedPolygon")
        _shader(L["CUSTOMSHADER"], "Twirl")
        _fx_on(L, "MOTIONBLUREFFECT")
    elif name in EXTRA_BUILTINS:
        cfg = EXTRA_BUILTINS[name]
        b = L["BARS"]
        b.set("Bars Setup/Bars/Shape Path", cfg["shape"])
        b.set("Bars Setup/Bars/Bar Count", cfg["count"])
        b.set("Bars Setup/Bars/Max Height Scale", cfg["height"])
        b.set("Bars Setup/Bars/Bar Width", cfg["width"])
        b.set("Bars Setup/Bars/Path Size", cfg["path"])
        b.set("Bars Setup/Bars/Bar Spacing", cfg["spacing"])
        b.set("General/Position/Position Y", cfg["y"])
        if cfg.get("mirror"):
            b.set("Segment 1/Segment 1/Mirror", True)
        if cfg.get("particles"):
            L["PARTICLES"].set("General/Layer/Visible", True)
            L["PARTICLES"].set("Overall Settings/Emitter/Count Limit", cfg["particles"])
            L["PARTICLES"].set("Overall Settings/Emitter/Spawn Area", cfg.get("spawn", "Circle"))
        if cfg.get("wave"):
            # WAVEFORM is optional, so create it only for presets that request it.
            # Keep it below TEXT so titles remain readable.
            wave = p.layer("WAVEFORM")
            p.layers.remove(wave)
            text_index = next((i for i, layer in enumerate(p.layers)
                               if layer.module == "TEXT"), len(p.layers))
            p.layers.insert(text_index, wave)
            L["WAVEFORM"] = wave
            wave.set("General/Layer/Visible", True)
        for module in cfg.get("effects", []):
            if module == "BLUREFFECT":
                _fx_on(L, module)
            elif module == "RGBSPLITEFFECT":
                _fx_on(L, module)
            elif module == "MIRROREREFFECT":
                _fx_on(L, module, **{"Appearance/Mirror/Mirror Mode": "Vertical"})
            elif module == "MOTIONBLUREFFECT":
                _fx_on(L, module)
        if cfg.get("shader"):
            _shader(L["CUSTOMSHADER"], cfg["shader"])
    else:
        raise KeyError(name)
    return p


def _shader(layer, preset):
    from .engine.shader_presets import apply_preset
    apply_preset(layer, preset)
    layer.set("General/Layer/Visible", True)


# Extra presets intentionally vary geometry, density, movement and effect stacks.
# Each entry has a distinct parameter combination; no duplicate placeholder looks.
EXTRA_BUILTINS = {
    "Aurora Ribbon": {"shape":"WaveformPath","count":72,"height":0.34,"width":0.72,"path":0.42,"spacing":0.12,"y":0.34,"wave":True,"effects":["BLUREFFECT"]},
    "Solar Flare": {"shape":"Star","count":144,"height":0.62,"width":0.34,"path":0.58,"spacing":0.08,"y":0.48,"effects":["RGBSPLITEFFECT","BLUREFFECT"]},
    "Neon Tunnel": {"shape":"SidedPolygon","count":128,"height":0.46,"width":0.48,"path":0.72,"spacing":0.16,"y":0.5,"shader":"Zoom Blur"},
    "Pulse Grid": {"shape":"Square","count":64,"height":0.28,"width":0.8,"path":0.3,"spacing":0.22,"y":0.42,"shader":"3D Box"},
    "Prism Orbit": {"shape":"Star","count":96,"height":0.55,"width":0.42,"path":0.66,"spacing":0.1,"y":0.5,"shader":"Kaleidoscope","effects":["RGBSPLITEFFECT"]},
    "Deep Wave": {"shape":"WaveformPath","count":112,"height":0.24,"width":0.62,"path":0.24,"spacing":0.06,"y":0.28,"mirror":True,"wave":True},
    "Vortex Bloom": {"shape":"SidedPolygon","count":160,"height":0.5,"width":0.3,"path":0.82,"spacing":0.14,"y":0.52,"shader":"Twirl","particles":650},
    "Starlight Dust": {"shape":"Circle","count":48,"height":0.2,"width":0.9,"path":0.5,"spacing":0.25,"y":0.5,"particles":1100,"spawn":"Circle"},
    "Crystal Halo": {"shape":"SidedPolygon","count":120,"height":0.38,"width":0.44,"path":0.9,"spacing":0.1,"y":0.5,"shader":"Kaleidoscope","effects":["MIRROREREFFECT"]},
    "Retro Pulse": {"shape":"Square","count":80,"height":0.44,"width":0.66,"path":0.36,"spacing":0.2,"y":0.38,"shader":"Film Grain"},
    "Ocean Oscillation": {"shape":"WaveformPath","count":88,"height":0.3,"width":0.58,"path":0.56,"spacing":0.09,"y":0.32,"wave":True,"effects":["MOTIONBLUREFFECT"]},
    "Comet Trail": {"shape":"HorizontalLine","count":56,"height":0.72,"width":0.26,"path":0.2,"spacing":0.04,"y":0.62,"mirror":True,"effects":["MOTIONBLUREFFECT","BLUREFFECT"]},
    "Mirror Cathedral": {"shape":"SidedPolygon","count":104,"height":0.52,"width":0.52,"path":0.76,"spacing":0.18,"y":0.5,"shader":"Reflection","effects":["MIRROREREFFECT"]},
    "Lime Circuit": {"shape":"Square","count":192,"height":0.22,"width":0.38,"path":0.64,"spacing":0.06,"y":0.46,"shader":"Color Correction"},
    "Eclipse Ring": {"shape":"Circle","count":136,"height":0.6,"width":0.3,"path":0.94,"spacing":0.12,"y":0.5,"shader":"Vignette","effects":["BLUREFFECT"]},
    "Spectrum Rain": {"shape":"VerticalLine","count":100,"height":0.72,"width":0.22,"path":0.18,"spacing":0.05,"y":0.24,"mirror":True},
    "Glass Refraction": {"shape":"WaveformPath","count":92,"height":0.42,"width":0.46,"path":0.7,"spacing":0.11,"y":0.5,"shader":"Reflection"},
    "Particle Storm": {"shape":"HorizontalLine","count":40,"height":0.3,"width":0.7,"path":0.34,"spacing":0.2,"y":0.5,"particles":1400,"spawn":"Rectangle","shader":"Twirl"},
    "Monochrome Reactor": {"shape":"SidedPolygon","count":152,"height":0.48,"width":0.36,"path":0.62,"spacing":0.07,"y":0.5,"shader":"Color Correction","effects":["MOTIONBLUREFFECT"]},
    "Electric Bloom": {"shape":"Star","count":176,"height":0.66,"width":0.28,"path":0.88,"spacing":0.09,"y":0.5,"shader":"Kaleidoscope","particles":500,"effects":["RGBSPLITEFFECT","BLUREFFECT"]},
}
BUILTINS = ["Circle Classic", "Linear Spectrum", "Mirror Wave", "Neon Kaleido", "Zoom Pulse",
            "Retro 3D Box", "Twirl Galaxy"] + list(EXTRA_BUILTINS)


# ---------------------------------------------------------------- serialize
def to_template(project, name, meta=None, thumbnail=None):
    now = int(time.time())
    m = {"author": "", "description": "", "tags": [], "created": now, "modified": now, "app_version": APP_VERSION}
    m.update(meta or {})
    m["modified"] = now
    try:
        comp = project.layer("COMPOSITION")
        m["size"] = [int(comp.get("Render Settings/Output/Resolution Width")),
                     int(comp.get("Render Settings/Output/Resolution Height"))]
    except Exception:
        pass
    m["layer_count"] = len(project.layers)
    data = {"format": FORMAT, "version": VERSION, "name": name, "meta": m,
            "layers": [l.to_dict() for l in project.layers]}
    if thumbnail:
        data["thumbnail"] = thumbnail
    return data


def migrate(data):
    """Upgrade older template dicts in place to the current version."""
    if not isinstance(data, dict):
        raise ValueError("Not a Vooc template")
    v = int(data.get("version") or 1)
    if v > VERSION:
        data.setdefault("warnings", []).append("made with a newer Vooc (v%d); unknown parts are skipped" % v)
    if v < 2:
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        meta.setdefault("author", "")
        meta.setdefault("description", "")
        meta.setdefault("tags", [])
        meta.setdefault("created", 0)
        meta.setdefault("modified", 0)
        meta.setdefault("app_version", "")
        data["meta"] = meta
        data["version"] = VERSION
    data["format"] = FORMAT
    if not isinstance(data.get("meta", {}).get("tags", []), list):
        data["meta"]["tags"] = [str(data["meta"]["tags"])]
    return data


def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get("layers"), list):
        raise ValueError("Not a Vooc template (missing layers)")
    if data.get("format") not in (FORMAT, None):
        raise ValueError("Unknown template format %r" % data.get("format"))
    layers = []
    for d in data["layers"]:
        try:
            layers.append(LayerModel.from_dict(d))
        except Exception:
            continue          # unknown module from a newer version: skip it
    if not layers:
        raise ValueError("Template has no usable layers")
    return layers


def check(data):
    """Validation report for import: (ok, problems[]) without raising."""
    problems = []
    try:
        migrate(data)
        layers = validate(data)
    except Exception as exc:
        return False, [str(exc)]
    skipped = len(data["layers"]) - len(layers)
    if skipped:
        problems.append("%d layer(s) from a newer version were skipped" % skipped)
    for p in asset_paths(data):
        if not os.path.isfile(p):
            problems.append("missing file: %s" % os.path.basename(p))
    return True, problems + list(data.get("warnings", []))


# ---------------------------------------------------------------- assets / bundles
def _asset_fields(module):
    from .property_schema import iter_fields
    return [path for path, spec in iter_fields(module) if spec.get("type") in ASSET_TYPES]


def asset_paths(data):
    out = []
    for d in data.get("layers", []):
        module, values = d.get("module"), d.get("values") or {}
        try:
            fields = _asset_fields(module)
        except Exception:
            continue
        for path in fields:
            v = values.get(path)
            if isinstance(v, str) and v and ("/" in v or os.sep in v) and v not in out:
                out.append(v)
    return out


def pack_bundle(data):
    """Template dict -> .vzb bytes with every referenced local file embedded."""
    assets, mapping = {}, {}
    for p in asset_paths(data):
        try:
            if not os.path.isfile(p) or os.path.getsize(p) > MAX_ASSET_BYTES:
                continue
            raw = Path(p).read_bytes()
        except OSError:
            continue
        key = hashlib.sha1(raw).hexdigest()[:12] + "_" + os.path.basename(p)
        assets[key] = base64.b64encode(raw).decode("ascii")
        mapping[p] = "asset:" + key
    tpl = json.loads(json.dumps(data))
    for d in tpl.get("layers", []):
        vals = d.get("values") or {}
        for k, v in list(vals.items()):
            if isinstance(v, str) and v in mapping:
                vals[k] = mapping[v]
    payload = json.dumps({"template": tpl, "assets": assets}, separators=(",", ":")).encode("utf-8")
    return BUNDLE_MAGIC + zlib.compress(payload, 9)


def unpack_bundle(raw, asset_dir):
    """.vzb bytes -> template dict; assets are written to ``asset_dir`` and paths rewritten."""
    if not raw.startswith(BUNDLE_MAGIC):
        raise ValueError("Not a Vooc bundle")
    try:
        doc = json.loads(zlib.decompress(raw[len(BUNDLE_MAGIC):]).decode("utf-8"))
    except Exception:
        raise ValueError("Bundle is damaged")
    tpl, assets = doc.get("template"), doc.get("assets") or {}
    if not isinstance(tpl, dict):
        raise ValueError("Bundle has no template")
    asset_dir = Path(asset_dir)
    paths = {}
    for key, b64 in assets.items():
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)[:120]
        asset_dir.mkdir(parents=True, exist_ok=True)
        f = asset_dir / safe
        if not f.exists():
            f.write_bytes(base64.b64decode(b64))
        paths["asset:" + key] = str(f)
    for d in tpl.get("layers", []):
        vals = d.get("values") or {}
        for k, v in list(vals.items()):
            if isinstance(v, str) and v.startswith("asset:"):
                vals[k] = paths.get(v, "")
    return tpl



def pack_avp(data):
    """Create a portable .avp ZIP package containing a preset and its local assets."""
    tpl = json.loads(json.dumps(data))
    assets = {}
    for original in asset_paths(tpl):
        if not os.path.isfile(original):
            raise ValueError("Preset asset is missing: %s" % os.path.basename(original))
        if os.path.getsize(original) > MAX_ASSET_BYTES:
            raise ValueError("Preset asset exceeds the 12 MB limit: %s" % os.path.basename(original))
        raw = Path(original).read_bytes()
        name = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.basename(original))[:100] or "asset.bin"
        archive_path = "assets/" + hashlib.sha1(raw).hexdigest()[:12] + "_" + name
        assets[archive_path] = raw
        for layer in tpl.get("layers", []):
            values = layer.get("values") or {}
            for field, value in list(values.items()):
                if value == original:
                    values[field] = "asset:" + archive_path
    tpl["format"] = FORMAT
    tpl["version"] = VERSION
    manifest = {"format": AVP_FORMAT, "version": AVP_VERSION, "preset": "preset.json",
                "asset_count": len(assets), "name": tpl.get("name", "Vooc Preset")}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, separators=(",", ":")))
        zf.writestr("preset.json", json.dumps(tpl, separators=(",", ":")))
        for name, raw in assets.items():
            zf.writestr(name, raw)
    return out.getvalue()


def unpack_avp(raw, asset_dir):
    """Safely read a .avp package and restore bundled assets into the private app directory."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw), "r")
    except Exception:
        raise ValueError("Not a valid AVP preset package")
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_AVP_ENTRIES:
            raise ValueError("Preset package contains too many files")
        if sum(max(0, item.file_size) for item in infos) > MAX_AVP_TOTAL_BYTES:
            raise ValueError("Preset package is larger than 64 MB")
        for item in infos:
            name = item.filename.replace("\\", "/")
            if name.startswith("/") or any(part == ".." for part in name.split("/")):
                raise ValueError("Preset package contains an unsafe file path")
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("format") != AVP_FORMAT:
                raise ValueError("Unknown AVP package format")
            if int(manifest.get("version", 0)) > AVP_VERSION:
                raise ValueError("This AVP preset was created by a newer Vooc version")
            if manifest.get("preset", "preset.json") != "preset.json":
                raise ValueError("Invalid preset entry in AVP manifest")
            tpl = json.loads(archive.read("preset.json").decode("utf-8"))
        except ValueError:
            raise
        except Exception:
            raise ValueError("AVP package is damaged or incomplete")
        if not isinstance(tpl, dict) or not isinstance(tpl.get("layers"), list):
            raise ValueError("AVP package does not contain a valid preset")
        asset_dir = Path(asset_dir)
        asset_dir.mkdir(parents=True, exist_ok=True)
        extracted = {}
        for item in infos:
            name = item.filename.replace("\\", "/")
            if not name.startswith("assets/") or name.endswith("/"):
                continue
            key = name[len("assets/"):]
            if not key or "/" in key or "\\" in key:
                raise ValueError("Invalid asset path in AVP package")
            raw_asset = archive.read(item)
            if len(raw_asset) > MAX_ASSET_BYTES:
                raise ValueError("An AVP asset exceeds the 12 MB limit")
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)[:120] or "asset.bin"
            target = asset_dir / safe
            if not target.exists() or target.stat().st_size != len(raw_asset):
                target.write_bytes(raw_asset)
            extracted["asset:" + name] = str(target)
        for layer in tpl.get("layers", []):
            values = layer.get("values") or {}
            for field, value in list(values.items()):
                if isinstance(value, str) and value.startswith("asset:"):
                    values[field] = extracted.get(value, "")
        return tpl


def _convert_avee_viz(data, name="Imported Avee preset"):
    """Best-effort import of JSON-based Avee .viz data.

    Avee has multiple private/variant preset schemas. We deliberately map only
    fields that can be identified unambiguously and reject files with no
    supported settings rather than silently importing a blank project.
    """
    if not isinstance(data, dict):
        raise ValueError("Unsupported .viz structure: expected a JSON object")
    found = {"count": None, "shape": None, "colors": []}
    color_re = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
    def walk(node, key=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k))
        elif isinstance(node, (list, tuple)):
            if "color" in key.lower() and len(node) in (3, 4) and all(isinstance(x, (int, float)) for x in node):
                vals = [float(x) for x in node]
                scale = 255.0 if max(vals or [0]) > 1.0 else 1.0
                rgb = [int(round(max(0.0, min(1.0, x / scale)) * 255)) for x in vals[:3]]
                alpha = int(round(max(0.0, min(1.0, vals[3] / scale)) * 255)) if len(vals) == 4 else 255
                found["colors"].append("#%02X%02X%02X%02X" % (rgb[0], rgb[1], rgb[2], alpha))
            else:
                for item in node:
                    walk(item, key)
        elif isinstance(node, str):
            if "color" in key.lower():
                match = color_re.match(node.strip())
                if match:
                    raw = match.group(1).upper()
                    found["colors"].append("#" + (raw if len(raw) == 8 else raw + "FF"))
            if "shape" in key.lower() or "type" in key.lower() or "element" in key.lower():
                val = node.strip().lower().replace("_", "").replace("-", "").replace(" ", "")
                shapes_map = {
                    "circle": "Circle", "ring": "Circle", "radial": "Circle",
                    "line": "HorizontalLine", "bars": "HorizontalLine", "bar": "HorizontalLine",
                    "wave": "WaveformPath", "waveform": "WaveformPath", "oscilloscope": "WaveformPath",
                    "star": "Star", "hexagon": "Hexagon", "square": "Square",
                    "rectangle": "Rectangle", "triangle": "Triangle", "heart": "Heart",
                    "polygon": "SidedPolygon", "dots": "Circle",
                }
                for token, mapped in shapes_map.items():
                    if token in val:
                        found["shape"] = mapped
                        break
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            k = key.lower().replace("_", "").replace("-", "").replace(" ", "")
            if ("bar" in k and "count" in k) or k in ("numberofbars", "barscount"):
                if 4 <= int(node) <= 256:
                    found["count"] = int(node)
    walk(data)
    if found["count"] is None and found["shape"] is None and not found["colors"]:
        raise ValueError("Avee .viz detected, but no supported bar count, shape or color fields could be mapped. This preset schema is not yet compatible.")
    project = ProjectModel()
    bars = project.layer("BARS")
    if found["count"] is not None:
        bars.set("Bars Setup/Bars/Bar Count", found["count"])
    if found["shape"] is not None:
        bars.set("Bars Setup/Bars/Shape Path", found["shape"])
    colors = []
    for value in found["colors"]:
        if value not in colors:
            colors.append(value)
    if colors:
        bars.set("Segment 1/Segment 1/Color From", colors[0])
        bars.set("Segment 1/Segment 1/Color To", colors[1] if len(colors) > 1 else colors[0])
        bars.set("Bar Style/Color/Color Mode", "Segment Gradient" if len(colors) > 1 else "Solid")
    mapped = []
    if found["count"] is not None:
        mapped.append("bar count")
    if found["shape"] is not None:
        mapped.append("shape")
    if colors:
        mapped.append("%d color(s)" % min(2, len(colors)))
    template = to_template(project, name, meta={
        "author": "Avee .viz importer",
        "description": "Partial import; mapped " + ", ".join(mapped) + ". Unrecognized Avee settings were skipped.",
        "tags": ["Avee import", "partial"],
    })
    template["warnings"] = ["Partial Avee .viz import: mapped " + ", ".join(mapped) +
                            "; unsupported preset properties were skipped."]
    return template


def read_any(path, asset_dir):
    raw = Path(path).read_bytes()
    if raw.startswith(BUNDLE_MAGIC):
        return unpack_bundle(raw, asset_dir)
    if raw.startswith(b"PK\x03\x04"):
        try:
            return unpack_avp(raw, asset_dir)
        except Exception as exc:
            raise ValueError("Unsupported preset archive (not a Vooc .avp/.vzb package): %s" % exc)
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        raise ValueError("Unsupported .viz encoding; this importer accepts JSON-based Avee presets and Vooc .viz files") from exc
    if isinstance(data, dict):
        layers = data.get("layers")
        looks_like_vooc = (data.get("format") in (FORMAT, AVP_FORMAT) or
                           (isinstance(layers, list) and layers and
                            isinstance(layers[0], dict) and "module" in layers[0] and "values" in layers[0]))
        if looks_like_vooc:
            return data
    return _convert_avee_viz(data, Path(path).stem)


# ---------------------------------------------------------------- thumbnails
def png_bytes(rgba, w, h):
    """Minimal PNG encoder (RGBA8, top-down rows)."""
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    stride = w * 4
    rows = b"".join(b"\x00" + bytes(rgba[y * stride:(y + 1) * stride]) for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def make_thumbnail(pixels, w, h, max_w=192, bottom_up=True):
    """Base64 PNG thumbnail from raw RGBA frame bytes."""
    import numpy as np
    arr = np.frombuffer(bytes(pixels), np.uint8).reshape(h, w, 4)
    if bottom_up:
        arr = arr[::-1]
    step = max(1, int(np.ceil(w / float(max_w))))
    small = np.ascontiguousarray(arr[::step, ::step])
    small[..., 3] = 255
    th, tw = small.shape[:2]
    return base64.b64encode(png_bytes(small.tobytes(), tw, th)).decode("ascii")


def apply_template(project, data):
    """Replace the project's look with a template. Returns the template name."""
    layers = validate(migrate(data))
    keep = {l.module: l for l in project.layers if l.module in KEEP_ON_APPLY}
    fresh = []
    for l in layers:
        if l.module in keep:
            fresh.append(keep.pop(l.module))
        else:
            l.id = uuid.uuid4().hex[:10]          # new renderers / shader passes
            fresh.append(l)
    fresh.extend(keep.values())
    project.layers = fresh
    present = {l.module for l in fresh}
    for module in DEFAULT_LAYER_ORDER:
        if module not in present:
            project.layer(module)
    return data.get("name") or "Template"


def builtin(name):
    return to_template(_builtin(name), name)


# ---------------------------------------------------------------- storage
class TemplateStore:
    def __init__(self, directory):
        self.dir = Path(directory)

    def _file(self, name):
        safe = re.sub(r"[^A-Za-z0-9 _.-]+", "_", name).strip() or "Template"
        return self.dir / (safe + ".viz")

    def _read(self, f):
        return migrate(json.loads(f.read_text(encoding="utf-8")))

    def names(self):
        if not self.dir.exists():
            return []
        out = []
        for f in sorted(self.dir.glob("*.viz"), key=lambda x: x.stat().st_mtime):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")).get("name") or f.stem)
            except Exception:
                continue
        return out

    def path(self, name):
        for f in self.dir.glob("*.viz"):
            try:
                if (json.loads(f.read_text(encoding="utf-8")).get("name") or f.stem) == name:
                    return f
            except Exception:
                continue
        return None

    def load(self, name):
        if name in BUILTINS:
            return builtin(name)
        f = self.path(name)
        if f is None:
            raise KeyError(name)
        return self._read(f)

    def info(self, name):
        """Metadata + thumbnail without layers (cheap for lists)."""
        try:
            d = self.load(name)
        except Exception:
            return {"name": name, "meta": {}, "thumbnail": None, "builtin": name in BUILTINS}
        return {"name": name, "meta": d.get("meta", {}), "thumbnail": d.get("thumbnail"),
                "builtin": name in BUILTINS}

    def _write(self, data):
        self.dir.mkdir(parents=True, exist_ok=True)
        f = self._file(data["name"])
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, f)
        return f

    def save(self, project, name, meta=None, thumbnail=None):
        old = None
        try:
            old = self.load(name) if name not in BUILTINS and self.path(name) else None
        except Exception:
            pass
        m = dict((old or {}).get("meta", {}))
        m.update(meta or {})
        if old and old.get("meta", {}).get("created"):
            m["created"] = old["meta"]["created"]
        return self._write(to_template(project, name, m, thumbnail or (old or {}).get("thumbnail")))

    def unique(self, name):
        base, i, n = name, 2, name
        while n in BUILTINS or self.path(n) is not None:
            n = "%s %d" % (base, i)
            i += 1
        return n

    def rename(self, old, new):
        if old in BUILTINS:
            raise ValueError("Built-in templates cannot be renamed")
        data = self.load(old)
        new = self.unique(new.strip() or old)
        f = self.path(old)
        data["name"] = new
        self._write(data)
        if f is not None and f != self._file(new):
            f.unlink()
        favs = self.favorites()
        if old in favs:
            favs[favs.index(old)] = new
            self._save_favs(favs)
        return new

    def duplicate(self, name):
        data = json.loads(json.dumps(self.load(name)))
        data["name"] = self.unique(name + " copy")
        data.setdefault("meta", {})["created"] = int(time.time())
        self._write(data)
        return data["name"]

    def delete(self, name):
        f = self.path(name)
        if f is not None:
            f.unlink()
        favs = self.favorites()
        if name in favs:
            favs.remove(name)
            self._save_favs(favs)

    # favorites
    def favorites(self):
        try:
            return list(json.loads((self.dir / "favorites.json").read_text(encoding="utf-8")))
        except Exception:
            return []

    def _save_favs(self, favs):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "favorites.json").write_text(json.dumps(favs), encoding="utf-8")

    def toggle_favorite(self, name):
        favs = self.favorites()
        if name in favs:
            favs.remove(name)
        else:
            favs.append(name)
        self._save_favs(favs)
        return name in favs

    # import / export
    def import_file(self, path):
        data = read_any(path, self.dir / "assets")
        ok, problems = check(data)
        if not ok:
            raise ValueError(problems[0])
        data["name"] = self.unique(data.get("name") or Path(path).stem)
        data.pop("warnings", None)
        self._write(data)
        self.last_problems = problems
        return data["name"]

    def export_bundle(self, name, out_dir):
        data = self.load(name)
        out = Path(out_dir) / (re.sub(r"[^A-Za-z0-9 _.-]+", "_", name).strip() + ".vzb")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pack_bundle(data))
        return out

    def export_avp(self, name, out_dir):
        """Export a complete, portable Vooc preset as a native .avp package."""
        data = self.load(name)
        out = Path(out_dir) / (re.sub(r"[^A-Za-z0-9 _.-]+", "_", name).strip() + ".avp")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pack_avp(data))
        return out
