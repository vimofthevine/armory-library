"""Evaluation components for CIFAR10 baseline."""
import art.attacks.evasion

import armory.baseline_models.pytorch.cifar
import armory.data.datasets
import armory.scenarios.image_classification
from charmory.evaluation import (
    Attack,
    Dataset,
    Evaluation,
    Metric,
    ModelConfig,
    Scenario,
    SysConfig,
)
from functools import partial

dataset = Dataset(
    function=armory.data.datasets.cifar10, framework="numpy", batch_size=64
)

model = ModelConfig(
    name="pytorch cifar",
    load_model=partial(
        armory.baseline_models.pytorch.cifar.get_art_model,
        model_kwargs={},
        wrapper_kwargs={},
        weights_path=None,
    ),
    fit=True,
    fit_kwargs={"nb_epochs": 20},
)

attack = Attack(
    function=art.attacks.evasion.ProjectedGradientDescent,
    kwargs={
        "batch_size": 1,
        "eps": 0.031,
        "eps_step": 0.007,
        "max_iter": 20,
        "num_random_init": 1,
        "random_eps": False,
        "targeted": False,
        "verbose": False,
    },
    knowledge="white",
    use_label=True,
    type=None,
)


scenario = Scenario(
    function=armory.scenarios.image_classification.ImageClassificationTask,
    kwargs={},
)

metric = Metric(
    profiler_type="basic",
    supported_metrics=["accuracy"],
    perturbation=["linf"],
    task=["categorical_accuracy"],
    means=True,
    record_metric_per_sample=False,
)

sysconfig = SysConfig(gpus=["all"], use_gpu=True)


baseline = Evaluation(
    name="cifar_baseline",
    description="Baseline cifar10 image classification",
    author="msw@example.com",
    dataset=dataset,
    model=model,
    attack=attack,
    scenario=scenario,
    defense=None,
    metric=metric,
    sysconfig=sysconfig,
)
