from typing import Optional, Union

import lightning.pytorch as pl

from armory.logs import log
from charmory.evaluation import Evaluation
from charmory.tasks.base import BaseEvaluationTask
from charmory.track import track_metrics


class Engine:
    def __init__(self, evaluation: Evaluation):
        self.evaluation = evaluation
        self.scenario = evaluation.scenario.function(self.evaluation)

    def train(self, nb_epochs=1):
        """
        Train the evaluation model using the configured training dataset.

        Args:
            nb_epochs: Number of epochs with which to perform training
        """
        assert self.evaluation.dataset.train_dataset is not None, (
            "Requested to train the model but the evaluation dataset does not "
            "provide a train_dataset"
        )
        log.info(
            f"Fitting {self.evaluation.model.name} model with "
            f"{self.evaluation.dataset.name} dataset..."
        )
        # TODO trainer defense when poisoning attacks are supported
        self.evaluation.model.model.fit_generator(
            self.evaluation.dataset.train_dataset,
            nb_epochs=nb_epochs,
        )

    def run(self):
        results = self.scenario.evaluate()
        track_metrics(results["results"]["metrics"])

        return results


class LightningEngine:
    def __init__(
        self,
        task: BaseEvaluationTask,
        limit_test_batches: Optional[Union[int, float]] = None,
    ):
        self.task = task
        self.trainer = pl.Trainer(
            inference_mode=False, limit_test_batches=limit_test_batches
        )

    def run(self):
        self.trainer.test(self.task)
        return dict(
            compute=self.task.evaluation.metric.profiler.results(),
            metrics=self.trainer.callback_metrics,
        )
