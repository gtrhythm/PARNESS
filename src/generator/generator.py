"""Generator 主类 - 代码生成入口"""

import logging
from typing import Optional
from .models import GenConfig, AnalysisResult, ExperimentDesign, GeneratedCode
from .network import NetworkGenerator
from .code import DatasetCodeGenerator, TrainCodeGenerator
from .config import ConfigGenerator


class Generator:
    def __init__(self, config: Optional[GenConfig] = None):
        self.config = config or GenConfig()
        self._setup_logging()
        self.network_gen = NetworkGenerator(framework=self.config.default_framework)
        self.dataset_gen = DatasetCodeGenerator()
        self.train_gen = TrainCodeGenerator()
        self.config_gen = ConfigGenerator()

    def _setup_logging(self) -> None:
        if self.config.enable_logging:
            logging.basicConfig(
                level=getattr(logging, self.config.log_level.upper(), logging.INFO),
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )
        self.logger = logging.getLogger(__name__)

    async def generate(
        self,
        analysis_result: AnalysisResult,
        experiment_design: ExperimentDesign,
    ) -> GeneratedCode:
        self.logger.info(f"Generating code for idea: {analysis_result.idea_id}")

        model_code = self.network_gen.generate(analysis_result, experiment_design)
        self.logger.info("Generated model code")

        dataset_code = self.dataset_gen.generate(analysis_result, experiment_design)
        self.logger.info("Generated dataset code")

        train_code = self.train_gen.generate(analysis_result, experiment_design)
        self.logger.info("Generated training code")

        config = self.config_gen.generate(analysis_result, experiment_design)
        dependencies = self.config_gen.generate_requirements(analysis_result, experiment_design)
        self.logger.info(f"Generated config with {len(dependencies)} dependencies")

        generated = GeneratedCode(
            idea_id=analysis_result.idea_id,
            model_code=model_code,
            dataset_code=dataset_code,
            train_code=train_code,
            config=config,
            dependencies=dependencies,
        )

        self.logger.info(f"Code generation completed for idea: {analysis_result.idea_id}")
        return generated
