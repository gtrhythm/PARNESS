"""Generator 模块 - 代码生成模块

根据论文分析和实验设计生成 PyTorch 模型代码、数据处理代码和训练脚本。

使用示例:
    from generator import Generator, GenConfig, AnalysisResult, ExperimentDesign

    config = GenConfig(output_dir="./output")
    generator = Generator(config)
    
    result = await generator.generate(analysis_result, experiment_design)
    result.save("./generated_code")
"""

from .models import (
    GenConfig,
    AnalysisResult,
    ExperimentDesign,
    GeneratedCode,
)
from .generator import Generator
from .network import NetworkGenerator
from .code import CodeGenerator, DatasetCodeGenerator, TrainCodeGenerator
from .config import ConfigGenerator

__version__ = "0.1.0"
__all__ = [
    "Generator",
    "GenConfig",
    "AnalysisResult",
    "ExperimentDesign",
    "GeneratedCode",
    "NetworkGenerator",
    "CodeGenerator",
    "DatasetCodeGenerator",
    "TrainCodeGenerator",
    "ConfigGenerator",
]
