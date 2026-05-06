"""CodeGenerator - 代码生成器基类和组合"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from .models import AnalysisResult, ExperimentDesign, GeneratedCode
from .network import NetworkGenerator
from .config import ConfigGenerator


class CodeGenerator(ABC):
    @abstractmethod
    def generate(self, analysis: AnalysisResult, experiment: ExperimentDesign) -> str:
        pass


class DatasetCodeGenerator(CodeGenerator):
    def generate(self, analysis: AnalysisResult, experiment: ExperimentDesign) -> str:
        dataset_name = experiment.dataset_name.replace(" ", "_").lower()
        class_name = f"{dataset_name.title().replace('_', '')}Dataset"

        return f"""import torch
from torch.utils.data import Dataset, DataLoader
from typing import Optional, Tuple
import numpy as np


class {class_name}(Dataset):
    def __init__(
        self,
        data_path: str,
        transform: Optional[callable] = None,
        target_transform: Optional[callable] = None,
    ):
        self.data_path = data_path
        self.transform = transform
        self.target_transform = target_transform
        self.samples = self._load_data()

    def _load_data(self) -> list:
        return []

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        sample, label = self.samples[idx]
        if self.transform:
            sample = self.transform(sample)
        if self.target_transform:
            label = self.target_transform(label)
        return sample, label


def create_dataloader(
    dataset: Dataset,
    batch_size: int = {experiment.batch_size},
    shuffle: bool = True,
    num_workers: int = 4,
) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=True,
    )


def get_{dataset_name}_dataloaders(
    data_dir: str,
    batch_size: int = {experiment.batch_size},
) -> Tuple[DataLoader, DataLoader]:
    train_dataset = {class_name}(data_dir, transform=None)
    val_dataset = {class_name}(data_dir, transform=None)
    
    train_loader = create_dataloader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = create_dataloader(val_dataset, batch_size=batch_size, shuffle=False)
    
    return train_loader, val_loader
"""


class TrainCodeGenerator(CodeGenerator):
    def __init__(self):
        self.network_gen = NetworkGenerator()
        self.config_gen = ConfigGenerator()

    def generate(self, analysis: AnalysisResult, experiment: ExperimentDesign) -> str:
        model_name = experiment.model_name.replace(" ", "_").replace("-", "_").lower()
        idea_title = analysis.idea_title.replace(" ", "_").replace("-", "_").lower()

        return f"""import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from typing import Optional, Dict, Any
import time
import logging

from model import create_model
from dataset import get_{model_name}_dataloaders

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def train_epoch(
    model: nn.Module,
    train_loader: DataLoader,
    criterion: nn.Module,
    optimizer: optim.Optimizer,
    device: torch.device,
) -> float:
    model.train()
    total_loss = 0.0
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = criterion(output, target)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    return total_loss / len(train_loader)


def evaluate(
    model: nn.Module,
    val_loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> Dict[str, float]:
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    with torch.no_grad():
        for data, target in val_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            total_loss += criterion(output, target).item()
            _, predicted = output.max(1)
            total += target.size(0)
            correct += predicted.eq(target).sum().item()
    return {{
        "loss": total_loss / len(val_loader),
        "accuracy": 100.0 * correct / total,
    }}


def train(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    config: Dict[str, Any],
    device: torch.device,
    num_epochs: int = {experiment.expected_epochs},
) -> nn.Module:
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.{experiment.optimizer.title()}(
        model.parameters(), 
        lr={experiment.learning_rate}
    )
    
    scheduler = None
    if "{experiment.scheduler}":
        scheduler = optim.lr_scheduler.{experiment.scheduler}(
            optimizer, 
            **{experiment.training_config.get("scheduler_params", {{}})}
        )
    
    best_val_acc = 0.0
    for epoch in range(num_epochs):
        train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
        val_metrics = evaluate(model, val_loader, criterion, device)
        
        if scheduler:
            scheduler.step()
        
        logger.info(
            f"Epoch {{epoch+1}}/{{num_epochs}} - "
            f"Train Loss: {{train_loss:.4f}}, "
            f"Val Loss: {{val_metrics['loss']:.4f}}, "
            f"Val Acc: {{val_metrics['accuracy']:.2f}}%"
        )
        
        if val_metrics['accuracy'] > best_val_acc:
            best_val_acc = val_metrics['accuracy']
            torch.save(model.state_dict(), "best_model.pth")
    
    return model


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {{device}}")
    
    model = create_model().to(device)
    train_loader, val_loader = get_{model_name}_dataloaders(
        "{experiment.dataset_path}",
        batch_size={experiment.batch_size},
    )
    
    config = {{
        "num_epochs": {experiment.expected_epochs},
        "batch_size": {experiment.batch_size},
        "learning_rate": {experiment.learning_rate},
        "optimizer": "{experiment.optimizer}",
    }}
    
    trained_model = train(model, train_loader, val_loader, config, device)
    logger.info("Training completed!")


if __name__ == "__main__":
    main()
"""
