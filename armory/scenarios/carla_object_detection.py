"""
CARLA object detection

Scenario Contributor: MITRE Corporation
"""

import logging
import copy

from armory.scenarios.scenario import Scenario
from armory.utils import metrics

logger = logging.getLogger(__name__)


class CarlaObjectDetectionTask(Scenario):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.skip_misclassified:
            raise ValueError(
                "skip_misclassified shouldn't be set for carla_object_detection scenario"
            )
        if self.skip_benign:
            raise ValueError(
                "skip_benign shouldn't be set for carla_object_detection scenario, as "
                "adversarial predictions are measured against benign predictions"
            )

    def load_dataset(self):
        if self.config["dataset"]["batch_size"] != 1:
            raise ValueError("batch_size must be 1 for evaluation.")
        super().load_dataset(eval_split_default="dev")

    def run_benign(self):
        x, y = self.x, self.y
        y_object, y_patch_metadata = y

        # convert dict to List[dict] to comply with ART format
        y_object = [y_object]

        x.flags.writeable = False

        with metrics.resource_context(name="Inference", **self.profiler_kwargs):
            y_pred = self.model.predict(x, **self.predict_kwargs)
        self.metrics_logger.update_task(y_object, y_pred)
        self.y_pred = y_pred

    def run_attack(self):
        x, y = self.x, self.y
        y_object, y_patch_metadata = y

        # convert dict to List[dict] to comply with ART format
        y_object = [y_object]

        with metrics.resource_context(name="Attack", **self.profiler_kwargs):
            if self.use_label:
                y_target = [y_object]
            elif self.targeted:
                y_target = self.label_targeter.generate(y_object)
            else:
                y_target = None

            x_adv = self.attack.generate(
                x=x,
                y=y_target,
                y_patch_metadata=[y_patch_metadata],
                **self.generate_kwargs
            )

        # Ensure that input sample isn't overwritten by model
        x_adv.flags.writeable = False
        y_pred_adv = self.model.predict(x_adv, **self.predict_kwargs)
        self.metrics_logger.update_task(y_object, y_pred_adv, adversarial=True)
        self.metrics_logger_wrt_benign_preds.update_task(
            self.y_pred, y_pred_adv, adversarial=True
        )
        if self.targeted:
            self.metrics_logger.update_task(
                y_target, y_pred_adv, adversarial=True, targeted=True
            )
        self.metrics_logger.update_perturbation(x, x_adv)

        # If using multimodal input, add a warning if depth channels are perturbed
        if x.shape[-1] == 6:
            if (x[..., 3:] != x_adv[..., 3:]).sum() > 0:
                logger.warning("Adversarial attack perturbed depth channels")

        self.x_adv, self.y_target, self.y_pred_adv = x_adv, y_target, y_pred_adv

    def export_samples(self, num_samples):
        if num_samples < 1:
            raise ValueError(
                f"num_samples should be greater than or equal to 1, received {num_samples}."
            )
        elif num_samples > self.test_dataset.batch_size:
            raise ValueError(
                f"num_samples should be less than or equal to batch size. Received num_samples of {num_samples} and batch_size of {self.test_dataset.batch_size}"
            )

        self.sample_exporter.export(
            self.x[:num_samples],
            x_adv=self.x_adv[:num_samples] if self.x_adv is not None else None,
            y=self.y[:num_samples] if self.y is not None else None,
            y_pred_clean=self.y_pred[:num_samples] if self.y_pred is not None else None,
            y_pred_adv=self.y_pred_adv[:num_samples]
            if self.y_pred_adv is not None
            else None,
            plot_bboxes=True,
            classes_to_skip=4,
        )

    def finalize_results(self):
        super(CarlaObjectDetectionTask, self).finalize_results()

        self.metrics_logger_wrt_benign_preds.log_task(
            adversarial=True, used_preds_as_labels=True
        )
        self.results_wrt_benign_preds = {
            metric_name + "_wrt_benign_preds": result
            for metric_name, result in self.metrics_logger_wrt_benign_preds.results().items()
        }
        self.results = {**self.results, **self.results_wrt_benign_preds}

    def _evaluate(self) -> dict:
        """
        Evaluate the config and return a results dict
        """
        self.load()

        # Add a MetricsLogger to measure adversarial results using benign predictions as labels
        self.metrics_logger_wrt_benign_preds = metrics.MetricsLogger()
        self.metrics_logger_wrt_benign_preds.adversarial_tasks = copy.deepcopy(
            self.metrics_logger.adversarial_tasks
        )

        self.evaluate_all()
        self.finalize_results()
        return self.results
