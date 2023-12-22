"""
Base Armory evaluation task
"""

from abc import ABC
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Optional

import lightning.pytorch as pl
from lightning.pytorch.loggers import MLFlowLogger
import torch

from charmory.export.sink import MlflowSink, Sink

if TYPE_CHECKING:
    from charmory.batch import Batch
    from charmory.evaluation import Evaluation, PerturbationProtocol

ExportAdapter = Callable[[Any], Any]
"""An adapter for exported data (e.g., images). """


class BaseEvaluationTask(pl.LightningModule, ABC):
    """Base Armory evaluation task"""

    def __init__(
        self,
        evaluation: "Evaluation",
        skip_benign: bool = False,
        skip_attack: bool = False,
        export_adapter: Optional[ExportAdapter] = None,
        export_every_n_batches: int = 0,
    ):
        """
        Initializes the task.

        Args:
            evaluation: Configuration for the evaluation
            skip_benign: Whether to skip the benign, unperturbed inference
            skip_attack: Whether to skip the adversarial, perturbed inference
            export_adapter: Optional, adapter to be applied to inference data
                prior to exporting to MLflow
            export_every_n_batches: Frequency at which batches will be exported
                to MLflow. A value of 0 means that no batches will be exported.
                The data that is exported is task-specific.
        """
        super().__init__()
        self.evaluation = evaluation
        self.model = evaluation.model
        self.skip_benign = skip_benign
        self.skip_attack = skip_attack
        self.export_adapter = export_adapter
        self.export_every_n_batches = export_every_n_batches
        self._exporter: Optional[Sink] = None

        # Make copies of user-configured metrics for each perturbation chain
        self.metrics = self.MetricsDict(
            {
                chain_name: self.MetricsDict(
                    {
                        metric_name: metric.clone()
                        for metric_name, metric in self.evaluation.metrics.items()
                    }
                )
                for chain_name in self.evaluation.perturbations.keys()
            }
        )

    ###
    # Inner classes
    ###

    class MetricsDict(torch.nn.ModuleDict):
        def update_metrics(self, batch: "Batch") -> None:
            for metric in self.values():
                metric.update(batch)

        def compute(self) -> Mapping[str, torch.Tensor]:
            return {name: metric.compute() for name, metric in self.items()}

        def reset(self) -> None:
            for metric in self.values():
                metric.reset()

    ###
    # Properties
    ###

    @property
    def exporter(self) -> Sink:
        """Sample exporter for the current evaluation run"""
        if self._exporter is None:
            logger = self.logger
            if isinstance(logger, MLFlowLogger):
                self._exporter = MlflowSink(logger.experiment, logger.run_id)
            else:
                self._exporter = Sink()
        return self._exporter

    ###
    # Internal methods
    ###

    def _should_export(self, batch_idx) -> bool:
        """
        Whether the specified batch should be exported, based on the
        `export_every_n_batches` value.
        """
        if self.export_every_n_batches == 0:
            return False
        return (batch_idx + 1) % self.export_every_n_batches == 0

    ###
    # Task evaluation methods
    ###

    def apply_perturbations(
        self, chain_name: str, batch: "Batch", chain: Iterable["PerturbationProtocol"]
    ):
        """
        Applies the given perturbation chain to the batch to produce the perturbed data
        to be given to the model
        """
        with self.evaluation.profiler.measure(f"{chain_name}/perturbation"):
            for perturbation in chain:
                with self.evaluation.profiler.measure(
                    f"{chain_name}/perturbation/{perturbation.name}"
                ):
                    metadata = perturbation.apply(batch)
                    if metadata is not None:
                        batch.metadata[f"perturbation.{perturbation.name}"] = metadata

    def evaluate(self, chain_name: str, batch: "Batch"):
        """Perform evaluation on batch"""
        with self.evaluation.profiler.measure(f"{chain_name}/predict"):
            self.evaluation.model.predict(batch)

    def update_metrics(self, chain_name: str, batch: "Batch"):
        self.metrics[chain_name].update_metrics(batch)

    def log_metric(self, name: str, metric: Any):
        if isinstance(metric, dict):
            for k, v in metric.items():
                self.log_metric(f"{name}/{k}", v)

        elif isinstance(metric, torch.Tensor):
            if len(metric.shape) == 0:
                self.log(name, metric)
            elif len(metric.shape) == 1:
                self.log_dict(
                    {f"{name}/{idx}": value for idx, value in enumerate(metric)},
                    sync_dist=True,
                )
            else:
                for idx, value in enumerate(metric):
                    self.log_metric(f"{name}/{idx}", value)

        else:
            self.log(name, metric)

    ###
    # LightningModule method overrides
    ###

    def setup(self, stage: str) -> None:
        self.evaluation.exporter.use_sink(self.exporter)

    def on_test_epoch_start(self) -> None:
        """Resets all metrics"""
        self.metrics.reset()
        return super().on_test_epoch_start()

    def test_step(self, batch, batch_idx):
        """
        Performs evaluations of the model for each configured perturbation chain
        """
        for chain_name, chain in self.evaluation.perturbations.items():
            chain_batch = batch.clone()
            chain_batch.metadata["perturbations"] = dict()

            with torch.enable_grad():
                self.apply_perturbations(chain_name, chain_batch, chain)
            self.evaluate(chain_name, chain_batch)
            self.update_metrics(chain_name, chain_batch)

            if self._should_export(batch_idx):
                self.evaluation.exporter.export(chain_name, batch_idx, chain_batch)

    def on_test_epoch_end(self) -> None:
        """Logs all metric results"""
        for chain_name, chain in self.metrics.items():
            for metric_name, metric in chain.items():
                self.log_metric(f"{chain_name}/{metric_name}", metric.compute())

        return super().on_test_epoch_end()
