"""
Pipeline Adapter Designer.

Given an adapter name and optional upstream/downstream module names,
reads their specs and auto-generates:
  1. Adapter spec (input/output contract)
  2. Adapter skeleton code
  3. YAML pipeline fragment

Usage:
    python scripts/design_adapter.py --name paper_reviewer --upstream paper_writer --downstream paper_editor
    python scripts/design_adapter.py --name my_adapter --upstream idea_evaluator
    python scripts/design_adapter.py --name my_adapter --downstream experiment_plan_generator
    python scripts/design_adapter.py --name my_adapter  # no upstream/downstream yet
"""
import argparse
import importlib
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))


def _get_adapter_class(module_name: str):
    try:
        from src.orchestrator.modules import _ADAPTERS
        entry = _ADAPTERS.get(module_name)
        if not entry:
            return None
        mod_path, cls_name = entry
        mod = importlib.import_module(mod_path)
        return getattr(mod, cls_name, None)
    except Exception:
        return None


def _get_spec(module_name: str) -> Dict:
    cls = _get_adapter_class(module_name)
    if not cls:
        print(f"WARNING: module '{module_name}' not found in registry or has no class", file=sys.stderr)
        return {"found": False, "module_name": module_name}
    input_spec = getattr(cls, "INPUT_SPEC", {})
    output_spec = getattr(cls, "OUTPUT_SPEC", {})
    if not input_spec and not output_spec:
        print(f"WARNING: module '{module_name}' has no INPUT_SPEC/OUTPUT_SPEC", file=sys.stderr)
    return {
        "found": True,
        "module_name": module_name,
        "class_name": cls.__name__,
        "input_spec": input_spec,
        "output_spec": output_spec,
    }


def _infer_input_contract_from_upstreams(upstream_names: List[str]) -> Dict:
    input_contract = {}
    for up_name in upstream_names:
        up_spec = _get_spec(up_name)
        if not up_spec["found"]:
            continue
        out_spec = up_spec.get("output_spec", {})
        if not out_spec:
            continue
        for field_name, field_spec in out_spec.items():
            if field_name.startswith("_"):
                continue
            field_type = field_spec.get("type", "any") if isinstance(field_spec, dict) else "any"
            input_contract[field_name] = {
                "type": field_type,
                "required": False,
                "_source": f"output.{up_name}.{field_name}",
                "description": f"<TODO: describe what this input provides>",
            }
    return input_contract


def _infer_output_contract_from_downstreams(downstream_names: List[str]) -> Dict:
    output_contract = {}
    for down_name in downstream_names:
        down_spec = _get_spec(down_name)
        if not down_spec["found"]:
            continue
        in_spec = down_spec.get("input_spec", {})
        if not in_spec:
            continue
        for field_name, field_spec in in_spec.items():
            if field_name.startswith("_"):
                continue
            field_type = field_spec.get("type", "any") if isinstance(field_spec, dict) else "any"
            output_contract[field_name] = {
                "type": field_type,
                "_consumed_by": f"{down_name}.{field_name}",
                "description": f"<TODO: describe what this output provides>",
            }
    return output_contract


def _build_input_mapping(upstream_names: List[str], input_contract: Dict) -> Dict:
    mapping = {}
    for field_name, field_info in input_contract.items():
        source = field_info.get("_source", "")
        if source:
            mapping[field_name] = source
        elif upstream_names:
            up = upstream_names[0]
            mapping[field_name] = f"output.{up}.{field_name}"
    return mapping


def _build_output_mapping(output_contract: Dict) -> Dict:
    mapping = {}
    for field_name in output_contract:
        mapping[field_name] = field_name
    return mapping


def _camel(name: str) -> str:
    return "".join(word.capitalize() for word in name.split("_"))


def _generate_skeleton(name: str, spec: Dict) -> str:
    input_spec_dict = {}
    for k, v in spec["input_contract"].items():
        entry = {"type": v.get("type", "any"), "required": v.get("required", False)}
        input_spec_dict[k] = entry

    output_spec_dict = {}
    for k, v in spec["output_contract"].items():
        output_spec_dict[k] = {"type": v.get("type", "any")}

    input_lines = []
    for k, v in spec["input_contract"].items():
        ftype = v.get("type", "any")
        if ftype == "dict":
            default = "{}"
        elif ftype == "list":
            default = "[]"
        elif ftype == "int":
            default = "0"
        elif ftype == "float":
            default = "0.0"
        elif ftype == "bool":
            default = "False"
        else:
            default = '""'
        if not v.get("required", False):
            input_lines.append(f'        {k} = inputs.get("{k}", {default})')
        else:
            input_lines.append(f'        {k} = inputs.get("{k}")')
            input_lines.append(f'        if {k} is None:')
            input_lines.append(f'            raise ValueError("{k} is required")')

    output_lines = []
    for k in spec["output_contract"]:
        output_lines.append(f'            "{k}": <TODO>,')

    class_name = f"{_camel(name)}Module"

    input_spec_json = json.dumps(input_spec_dict, indent=4, ensure_ascii=False)
    output_spec_json = json.dumps(output_spec_dict, indent=4, ensure_ascii=False)

    input_spec_indented = "\n".join("    " + line for line in input_spec_json.splitlines())
    output_spec_indented = "\n".join("    " + line for line in output_spec_json.splitlines())

    skeleton = f'''from typing import Any, Dict
from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput


class {class_name}(LLMAgentModule):
    module_name = "{name}"

    INPUT_SPEC = {input_spec_indented}

    OUTPUT_SPEC = {output_spec_indented}

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
{chr(10).join(input_lines)}

        llm_client = self._get_llm_client()

        # TODO: build prompt from inputs
        # prompt = f"..."
        # response = await llm_client.chat(prompt)
        # parsed = json.loads(response) or response

        return {{
{chr(10).join(output_lines)}
        }}

    def emit_output(self, result):
        return AgentOutput(
            display_type="text",
            title="{name}",
            content=str(result),
        )
'''
    return skeleton


def _generate_yaml_fragment(name: str, upstream_names: List[str],
                            input_mapping: Dict, output_mapping: Dict) -> Dict:
    depends_on = upstream_names if upstream_names else []
    return {
        "id": name,
        "module": name,
        "depends_on": depends_on,
        "input_mapping": input_mapping,
        "output_mapping": output_mapping,
    }


def main():
    parser = argparse.ArgumentParser(description="Design a pipeline adapter")
    parser.add_argument("--name", required=True, help="Adapter module name")
    parser.add_argument("--upstream", action="append", default=[],
                        help="Upstream adapter module name (can specify multiple)")
    parser.add_argument("--downstream", action="append", default=[],
                        help="Downstream adapter module name (can specify multiple)")
    parser.add_argument("--output-dir", default=None,
                        help="Write generated files to this dir")
    args = parser.parse_args()

    upstream_names = args.upstream
    downstream_names = args.downstream

    input_contract = _infer_input_contract_from_upstreams(upstream_names)
    output_contract = _infer_output_contract_from_downstreams(downstream_names)

    if not input_contract and not output_contract:
        input_contract = {"data": {"type": "any", "required": False,
                                   "description": "<TODO: main input>"}}
        output_contract = {"result": {"type": "any",
                                      "description": "<TODO: main output>"}}

    spec = {
        "module": args.name,
        "input_contract": input_contract,
        "output_contract": output_contract,
    }

    input_mapping = _build_input_mapping(upstream_names, input_contract)
    output_mapping = _build_output_mapping(output_contract)

    yaml_fragment = _generate_yaml_fragment(args.name, upstream_names,
                                            input_mapping, output_mapping)

    skeleton_code = _generate_skeleton(args.name, spec)

    needs_llm_fill = ["description", "prompt_template"]
    for k, v in input_contract.items():
        if "<TODO" in v.get("description", ""):
            needs_llm_fill.append(f"input_contract.{k}.description")
    for k, v in output_contract.items():
        if "<TODO" in v.get("description", ""):
            needs_llm_fill.append(f"output_contract.{k}.description")

    output = {
        "spec": spec,
        "yaml_fragment": yaml_fragment,
        "skeleton_code": skeleton_code,
        "needs_llm_fill": needs_llm_fill,
    }

    if args.output_dir:
        out_dir = os.path.join(args.output_dir, args.name)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "spec.json"), "w") as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)
        with open(os.path.join(out_dir, f"{args.name}.py"), "w") as f:
            f.write(skeleton_code)
        with open(os.path.join(out_dir, "pipeline_fragment.yaml"), "w") as f:
            json.dump(yaml_fragment, f, indent=2, ensure_ascii=False)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
