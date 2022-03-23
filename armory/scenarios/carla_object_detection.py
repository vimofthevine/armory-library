"""
CARLA object detection

Scenario Contributor: MITRE Corporation
"""

import copy

from armory.scenarios.scenario import Scenario
from armory.utils import metrics
from armory.utils.export import ObjectDetectionExporter
from armory.logs import log


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

    def next(self):
        x, y = next(self.test_dataset)
        i = self.i + 1
        self.i, self.x, self.y = i, x, y
        self.y_object = [y[0]]
        self.y_patch_metadata = [y[1]]
        self.y_pred, self.y_target, self.x_adv, self.y_pred_adv = None, None, None, None

    def run_benign(self):
        x, y = self.x, self.y_object

        x.flags.writeable = False

        with metrics.resource_context(name="Inference", **self.profiler_kwargs):
            y_pred = self.model.predict(x, **self.predict_kwargs)
        self.metrics_logger.update_task(y, y_pred)
        self.y_pred = y_pred

    def run_attack(self):
        x, y = self.x, self.y_object

        with metrics.resource_context(name="Attack", **self.profiler_kwargs):
            if self.use_label:
                y_target = y
            elif self.targeted:
                y_target = self.label_targeter.generate(y)
            else:
                y_target = None

            x_adv = self.attack.generate(
                x=x,
                y=y_target,
                y_patch_metadata=self.y_patch_metadata,
                **self.generate_kwargs,
            )

        # Ensure that input sample isn't overwritten by model
        x_adv.flags.writeable = False
        y_pred_adv = self.model.predict(x_adv, **self.predict_kwargs)
        self.metrics_logger.update_task(y, y_pred_adv, adversarial=True)
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
                log.warning("Adversarial attack perturbed depth channels")

        self.x_adv, self.y_target, self.y_pred_adv = x_adv, y_target, y_pred_adv

    def _load_sample_exporter(self):
        return ObjectDetectionExporter(self.scenario_output_dir)

    def export_samples(self):
        self._check_x("export_samples")
        self.sample_exporter.export(
            self.x,
            x_adv=self.x_adv,
            y=self.y_object,
            y_pred_clean=self.y_pred,
            y_pred_adv=self.y_pred_adv,
            classes_to_skip=[4],
            with_boxes=True,
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
