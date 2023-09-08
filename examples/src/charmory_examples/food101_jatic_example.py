import pathlib
import sys

import art.attacks.evasion
from jatic_toolbox import load_dataset as load_jatic_dataset
from torchvision import transforms as T

import armory.baseline_models.pytorch.food101
import armory.data.datasets
from armory.instrument.config import MetricsLogger
from armory.metrics.compute import BasicProfiler
import armory.version
from charmory.data import JaticVisionDatasetGenerator
from charmory.evaluation import Attack, Dataset, Evaluation, Metric, Model, SysConfig
from charmory.experimental.lightning_execution import execute_lightning, print_outputs
from charmory.tasks.image_classification import ImageClassificationTask
from charmory.utils import PILtoNumpy

BATCH_SIZE = 16
TRAINING_EPOCHS = 1


def join_string(list_string):
    new_string = "/".join(list_string)
    return new_string


path = str(pathlib.Path().resolve()).split("/")[:3]
ROOT = join_string(path) + "/cache"


def load_torchvision_dataset(root_path):
    print("Loading torchvision dataset from jatic_toolbox")
    train_dataset = load_jatic_dataset(
        provider="torchvision",
        dataset_name="Food101",
        task="image-classification",
        split="train",
        root=root_path,
        download=True,
        transform=T.Compose(
            [
                T.Resize(size=(512, 512)),
                PILtoNumpy(),
            ]
        ),
    )
    train_dataset_generator = JaticVisionDatasetGenerator(
        dataset=train_dataset,
        batch_size=BATCH_SIZE,
        epochs=TRAINING_EPOCHS,
        shuffle=True,
    )
    test_dataset = load_jatic_dataset(
        provider="torchvision",
        dataset_name="Food101",
        task="image-classification",
        split="test",
        root=root_path,
        download=True,
        transform=T.Compose(
            [
                T.Resize(size=(512, 512)),
                PILtoNumpy(),
            ]
        ),
    )
    test_dataset_generator = JaticVisionDatasetGenerator(
        dataset=test_dataset,
        batch_size=BATCH_SIZE,
        epochs=1,
        shuffle=False,
    )

    return train_dataset_generator, test_dataset_generator


def main():
    train_dataset, test_dataset = load_torchvision_dataset(ROOT)

    dataset = Dataset(
        name="Food101",
        train_dataset=train_dataset,
        test_dataset=test_dataset,
    )
    classifier = armory.baseline_models.pytorch.food101.get_art_model(
        model_kwargs={},
        wrapper_kwargs={},
        weights_path=None,
    )
    model = Model(
        name="Food101",
        model=classifier,
    )

    ###
    # The rest of this file was directly copied from the existing cifar example
    ###

    attack = Attack(
        name="PGD",
        attack=art.attacks.evasion.ProjectedGradientDescent(
            classifier,
            batch_size=1,
            eps=0.031,
            eps_step=0.007,
            max_iter=20,
            num_random_init=1,
            random_eps=False,
            targeted=False,
            verbose=False,
        ),
        use_label_for_untargeted=True,
    )

    metric = Metric(
        profiler=BasicProfiler(),
        logger=MetricsLogger(
            supported_metrics=["accuracy"],
            perturbation=["linf"],
            task=["categorical_accuracy"],
            means=True,
            record_metric_per_sample=False,
        ),
    )

    sysconfig = SysConfig(gpus=["all"], use_gpu=True)

    evaluation = Evaluation(
        name="food101_baseline",
        description="Baseline food101 image classification",
        author="msw@example.com",
        dataset=dataset,
        model=model,
        attack=attack,
        scenario=None,
        metric=metric,
        sysconfig=sysconfig,
    )

    task = ImageClassificationTask(
        evaluation, num_classes=101, export_every_n_batches=5
    )

    results = execute_lightning(task, limit_test_batches=5)
    print_outputs(dataset, model, results)

    print("JATIC Experiment Complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
