import argparse
from pprint import pprint

from art.attacks.evasion import ProjectedGradientDescent
from art.estimators.classification import PyTorchClassifier
import datasets
import torch
import torch.nn
import torchmetrics.classification
from transformers import AutoImageProcessor, AutoModelForImageClassification

from armory.metrics.compute import BasicProfiler
from charmory.data import ArmoryDataLoader
from charmory.engine import EvaluationEngine
import charmory.evaluation as ev
from charmory.metrics.perturbation import PerturbationNormMetric
from charmory.model.image_classification import JaticImageClassificationModel
from charmory.tasks.image_classification import ImageClassificationTask
from charmory.track import track_init_params, track_params
from charmory.utils import Unnormalize


def get_cli_args():
    parser = argparse.ArgumentParser(
        description="MNIST image classification using a ViT model and PGD attack",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--batch-size",
        default=16,
        type=int,
    )
    parser.add_argument(
        "--export-every-n-batches",
        default=5,
        type=int,
    )
    parser.add_argument(
        "--num-batches",
        default=10,
        type=int,
    )
    return parser.parse_args()


@track_params
def main(batch_size, export_every_n_batches, num_batches):
    ###
    # Model
    ###
    model = JaticImageClassificationModel(
        track_params(AutoModelForImageClassification.from_pretrained)(
            "farleyknight-org-username/vit-base-mnist"
        ),
    )
    classifier = track_init_params(PyTorchClassifier)(
        model,
        loss=torch.nn.CrossEntropyLoss(),
        optimizer=torch.optim.Adam(model.parameters(), lr=0.003),
        input_shape=(3, 224, 224),
        channels_first=True,
        nb_classes=10,
        clip_values=(-1, 1),
    )

    ###
    # Dataset
    ###
    dataset = datasets.load_dataset("mnist", split="test")
    processor = AutoImageProcessor.from_pretrained(
        "farleyknight-org-username/vit-base-mnist"
    )

    def transform(sample):
        # Use the HF image processor and convert from BW To RGB
        sample["image"] = processor([img.convert("RGB") for img in sample["image"]])[
            "pixel_values"
        ]
        return sample

    dataset.set_transform(transform)
    dataloader = ArmoryDataLoader(dataset, batch_size=batch_size, num_workers=5)

    ###
    # Attack
    ###
    pgd = track_init_params(ProjectedGradientDescent)(
        classifier,
        batch_size=batch_size,
        eps=0.031,
        eps_step=0.007,
        max_iter=20,
        num_random_init=1,
        random_eps=False,
        targeted=False,
        verbose=False,
    )

    pgd_attack = ev.Attack(
        name="PGD",
        attack=pgd,
        use_label_for_untargeted=False,
    )

    ###
    # Metrics
    ###
    metric = ev.Metric(
        profiler=BasicProfiler(),
        perturbation={
            "linf_norm": PerturbationNormMetric(ord=torch.inf),
        },
        prediction={
            "accuracy_avg": torchmetrics.classification.Accuracy(
                task="multiclass", num_classes=10
            ),
            "accuracy_by_class": torchmetrics.classification.Accuracy(
                task="multiclass", num_classes=10, average=None
            ),
            "precision_avg": torchmetrics.classification.Precision(
                task="multiclass", num_classes=10
            ),
            "precision_by_class": torchmetrics.classification.Precision(
                task="multiclass", num_classes=10, average=None
            ),
            "recall_avg": torchmetrics.classification.Recall(
                task="multiclass", num_classes=10
            ),
            "recall_by_class": torchmetrics.classification.Recall(
                task="multiclass", num_classes=10, average=None
            ),
            "f1_score_avg": torchmetrics.classification.F1Score(
                task="multiclass", num_classes=10
            ),
            "f1_score_by_class": torchmetrics.classification.F1Score(
                task="multiclass", num_classes=10, average=None
            ),
            "confusion": torchmetrics.classification.ConfusionMatrix(
                task="multiclass", num_classes=10
            ),
        },
    )

    ###
    # Evaluation
    ###
    evaluation = ev.Evaluation(
        name="mnist-vit-pgd",
        description="MNIST image classification using a ViT model and PGD attack",
        author="TwoSix",
        dataset=ev.Dataset(
            name="MNIST",
            x_key="image",
            y_key="label",
            test_dataloader=dataloader,
        ),
        model=ev.Model(
            name="ViT",
            model=classifier,
        ),
        perturbations={
            "benign": [],
            "attack": [pgd_attack],
        },
        metric=metric,
    )

    ###
    # Engine
    ###
    task = ImageClassificationTask(
        evaluation,
        export_adapter=Unnormalize(mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5)),
        export_every_n_batches=export_every_n_batches,
    )
    engine = EvaluationEngine(task, limit_test_batches=num_batches)

    ###
    # Execute
    ###
    pprint(engine.run())


if __name__ == "__main__":
    main(**vars(get_cli_args()))
