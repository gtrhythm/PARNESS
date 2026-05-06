"""NetworkGenerator - 网络结构代码生成"""

from typing import Dict, Any, List
from .models import AnalysisResult, ExperimentDesign


class NetworkGenerator:
    def __init__(self, framework: str = "pytorch"):
        self.framework = framework

    def generate(self, analysis: AnalysisResult, experiment: ExperimentDesign) -> str:
        idea_title = analysis.idea_title.replace(" ", "_").replace("-", "_").lower()
        class_name = "".join(word.capitalize() for word in idea_title.split("_")) + "Model"

        imports = self._generate_imports()
        model_class = self._generate_model_class(class_name, analysis, experiment)
        forward_method = self._generate_forward_method(analysis, experiment)

        return f"""{imports}

class {class_name}(torch.nn.Module):
    def __init__(self, num_classes: int = {self._get_num_classes(experiment)}):
        super().__init__()
        self.num_classes = num_classes
{self._indent_code(model_class, 4)}
{self._indent_code(forward_method, 4)}

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self._forward_impl(x)


def create_model(num_classes: int = {self._get_num_classes(experiment)}) -> {class_name}:
    return {class_name}(num_classes=num_classes)
"""

    def _generate_imports(self) -> str:
        if self.framework == "pytorch":
            return "import torch\nimport torch.nn as nn\nimport torch.nn.functional as F"
        return "import torch\nimport torch.nn as nn"

    def _generate_model_class(self, class_name: str, analysis: AnalysisResult, experiment: ExperimentDesign) -> str:
        lines = []
        for i, component in enumerate(analysis.key_components[:5]):
            component_name = component.replace(" ", "_").lower()
            lines.append(f"self.{component_name}_layer = nn.Linear(512, 256)")

        lines.append(f"self.classifier = nn.Linear(256, self.num_classes)")
        return "\n".join(lines) if lines else "self.classifier = nn.Linear(512, self.num_classes)"

    def _generate_forward_method(self, analysis: AnalysisResult, experiment: ExperimentDesign) -> str:
        return """x = self.flatten(x) if hasattr(self, 'flatten') else x.view(x.size(0), -1)
        for component in analysis.key_components[:5]:
            component_name = component.replace(" ", "_").lower()
            if hasattr(self, f'{component_name}_layer'):
                x = F.relu(getattr(self, f'{component_name}_layer')(x))
        x = self.classifier(x)
        return x"""

    def _get_num_classes(self, experiment: ExperimentDesign) -> int:
        return experiment.training_config.get("num_classes", 10)

    def _indent_code(self, code: str, spaces: int) -> str:
        indent = " " * spaces
        return "\n".join(f"{indent}{line}" for line in code.split("\n"))
