#!/usr/bin/env python3
"""
Pipeline Adapter Interface Validator.

Validates that all adapter input/output connections in a pipeline YAML are correct.

Usage:
    python scripts/validate_pipeline.py config/pipelines/simple_idea_test.yaml
    python scripts/validate_pipeline.py config/pipelines/  # validate all yaml files in dir

Checks per edge (upstream → downstream):
  a. STRUCTURE:      Does input_mapping reference a node that exists?
  b. FIELD EXISTS:   Does output.node_id.field_name exist in upstream OUTPUT_SPEC?
  c. TYPE MATCH:     Does the type in upstream OUTPUT_SPEC match downstream INPUT_SPEC?
  d. REQUIRED COV:   Are all required inputs in downstream INPUT_SPEC provided?
  e. DANGLING REF:   Does input_mapping reference a node not in depends_on?
"""
import importlib
import json
import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from src.orchestrator.iteration.graph import IterationGraph, IterationNode
from src.orchestrator.modules import _ADAPTERS, register_all_modules
from src.orchestrator.registry import ModuleRegistry


def _load_adapter_class(module_name: str):
    entry = _ADAPTERS.get(module_name)
    if not entry:
        return None
    mod_path, cls_name = entry
    try:
        mod = importlib.import_module(mod_path)
        return getattr(mod, cls_name, None)
    except Exception:
        return None


def _get_specs(cls) -> Tuple[dict, dict]:
    if cls is None:
        return {}, {}
    input_spec = getattr(cls, "INPUT_SPEC", None)
    output_spec = getattr(cls, "OUTPUT_SPEC", None)
    return input_spec or {}, output_spec or {}


def _type_str(spec_entry: dict) -> str:
    if not spec_entry:
        return "any"
    return str(spec_entry.get("type", "any"))


def _types_compatible(src_type: str, dst_type: str) -> bool:
    if not src_type or not dst_type or src_type == "any" or dst_type == "any":
        return True
    return src_type == dst_type


def _resolve_config_key(key: str, config: dict) -> bool:
    parts = key.split(".")
    obj = config
    for part in parts:
        if isinstance(obj, dict):
            if part not in obj:
                return False
            obj = obj[part]
        else:
            return False
    return True


def validate_pipeline(yaml_path: str) -> List[dict]:
    results = []
    graph = IterationGraph.from_yaml(yaml_path)

    node_map: Dict[str, IterationNode] = {}
    for nid, node in graph.nodes.items():
        if node.module_name:
            node_map[nid] = node

    node_specs: Dict[str, dict] = {}
    for nid, node in node_map.items():
        cls = _load_adapter_class(node.module_name)
        inp, out = _get_specs(cls)
        node_specs[nid] = {"input_spec": inp, "output_spec": out, "class": cls}
        if cls is None:
            results.append({
                "level": "WARN",
                "node": nid,
                "check": "STRUCTURE",
                "message": f"module '{node.module_name}' not found in adapter registry, skipping spec checks",
            })
        elif not getattr(cls, "INPUT_SPEC", None) and not getattr(cls, "OUTPUT_SPEC", None):
            results.append({
                "level": "WARN",
                "node": nid,
                "check": "STRUCTURE",
                "message": f"adapter '{node.module_name}' has no INPUT_SPEC/OUTPUT_SPEC, skipping spec checks",
            })

    for nid, node in node_map.items():
        spec = node_specs[nid]
        inp_spec = spec["input_spec"]

        for param_name, ctx_key in node.input_mapping.items():
            if not isinstance(ctx_key, str):
                results.append({
                    "level": "PASS",
                    "node": nid,
                    "check": "STRUCTURE",
                    "message": f"{type(ctx_key).__name__} value → {nid}.{param_name} (literal)",
                })
                continue

            if ctx_key.startswith("config."):
                config_key = ctx_key[len("config."):]
                if _resolve_config_key(config_key, graph.config):
                    results.append({
                        "level": "PASS",
                        "node": nid,
                        "check": "STRUCTURE",
                        "message": f"config.{config_key} → {nid}.{param_name}",
                    })
                else:
                    results.append({
                        "level": "FAIL",
                        "node": nid,
                        "check": "STRUCTURE",
                        "message": f"config.{config_key} → {nid}.{param_name}: key '{config_key}' not found in pipeline config",
                    })
                continue

            if ctx_key.startswith("output."):
                parts = ctx_key.split(".", 2)
                if len(parts) < 3:
                    results.append({
                        "level": "FAIL",
                        "node": nid,
                        "check": "STRUCTURE",
                        "message": f"malformed output reference '{ctx_key}' for {nid}.{param_name} — expected output.node_id.field_name",
                    })
                    continue

                src_node_id = parts[1]
                field_name = parts[2]

                # (a) STRUCTURE: does the referenced node exist?
                if src_node_id not in graph.nodes:
                    results.append({
                        "level": "FAIL",
                        "node": nid,
                        "check": "STRUCTURE",
                        "message": f"upstream node '{src_node_id}' referenced in input_mapping does not exist in pipeline",
                    })
                    continue

                src_spec_data = node_specs.get(src_node_id, {})
                src_out_spec = src_spec_data.get("output_spec", {})
                src_node = node_map.get(src_node_id)

                # Resolve output_mapping: the field_name in ctx_key refers to the
                # *mapped* (output_mapping value) name, so we reverse it to find
                # the actual output key from the adapter.
                actual_field = field_name
                if src_node and src_node.output_mapping:
                    reverse_map = {v: k for k, v in src_node.output_mapping.items()}
                    if field_name in reverse_map:
                        actual_field = reverse_map[field_name]

                # (b) FIELD EXISTS: does the field exist in upstream OUTPUT_SPEC?
                if src_out_spec and actual_field not in src_out_spec:
                    results.append({
                        "level": "FAIL",
                        "node": nid,
                        "check": "FIELD_EXISTS",
                        "message": f"field '{actual_field}' not in {src_node_id} OUTPUT_SPEC {list(src_out_spec.keys())}",
                    })
                elif src_out_spec:
                    results.append({
                        "level": "PASS",
                        "node": nid,
                        "check": "FIELD_EXISTS",
                        "message": f"{src_node_id}.{actual_field} exists in OUTPUT_SPEC",
                    })

                # (c) TYPE MATCH: does upstream output type match downstream input type?
                if src_out_spec and inp_spec:
                    src_field_spec = src_out_spec.get(actual_field, {})
                    dst_field_spec = inp_spec.get(param_name, {})
                    src_type = _type_str(src_field_spec)
                    dst_type = _type_str(dst_field_spec)
                    if not _types_compatible(src_type, dst_type):
                        results.append({
                            "level": "WARN",
                            "node": nid,
                            "check": "TYPE_MATCH",
                            "message": f"{src_node_id}.{actual_field}({src_type}) → {nid}.{param_name}({dst_type}): type mismatch (may work at runtime)",
                        })
                    else:
                        results.append({
                            "level": "PASS",
                            "node": nid,
                            "check": "TYPE_MATCH",
                            "message": f"{src_node_id}.{actual_field}({src_type}) → {nid}.{param_name}({dst_type})",
                        })

                # (e) DANGLING REF: does input_mapping reference a node not in depends_on?
                if src_node_id not in node.depends_on:
                    results.append({
                        "level": "WARN",
                        "node": nid,
                        "check": "DANGLING_REF",
                        "message": f"'{src_node_id}' referenced in input_mapping but not in depends_on — execution order not guaranteed",
                    })

                continue

            # Static / literal value reference
            results.append({
                "level": "PASS",
                "node": nid,
                "check": "STRUCTURE",
                "message": f"{ctx_key} → {nid}.{param_name} (literal/param)",
            })

        # (d) REQUIRED COVERAGE: are all required inputs provided?
        if inp_spec:
            provided = set(node.input_mapping.keys())
            for key, spec in inp_spec.items():
                if spec.get("required", False) and key not in provided:
                    results.append({
                        "level": "FAIL",
                        "node": nid,
                        "check": "REQUIRED_COVERAGE",
                        "message": f"required input '{key}' not provided in input_mapping",
                    })
                elif key in provided:
                    pass

    return results


def format_results(results: List[dict]) -> str:
    lines = []
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}

    for r in results:
        level = r["level"]
        check = r.get("check", "")
        msg = r["message"]
        counts[level] = counts.get(level, 0) + 1

        if level == "PASS":
            lines.append(f"  [PASS] {check}: {msg}")
        elif level == "WARN":
            lines.append(f"  [WARN] {check}: {msg}")
        else:
            lines.append(f"  [FAIL] {check}: {msg}")

    lines.append("")
    lines.append(f"{counts['PASS']} passed, {counts['WARN']} warnings, {counts['FAIL']} failures")
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate pipeline adapter interfaces")
    parser.add_argument("path", help="Pipeline YAML file or directory of YAML files")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    path = Path(args.path)
    if path.is_dir():
        files = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml"))
        files = sorted(set(files))
    else:
        files = [path]

    any_fail = False
    all_results = {}
    for f in files:
        try:
            results = validate_pipeline(str(f))
        except Exception as e:
            if args.json:
                all_results[str(f)] = [{"level": "FAIL", "check": "LOAD", "message": str(e)}]
            else:
                print(f"\n{'=' * 60}")
                print(f"Pipeline: {f}")
                print(f"{'=' * 60}")
                print(f"  [FAIL] Could not load pipeline: {e}")
            any_fail = True
            continue

        if args.json:
            all_results[str(f)] = results
        else:
            print(f"\n{'=' * 60}")
            print(f"Pipeline: {f}")
            print(f"{'=' * 60}")
            print(format_results(results))

        if any(r["level"] == "FAIL" for r in results):
            any_fail = True

    if args.json:
        print(json.dumps(all_results, indent=2, ensure_ascii=False))

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
