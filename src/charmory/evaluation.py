"""Armory Experiment Configuration Classes"""

# TODO: review the Optionals with @woodall

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional

from armory.data.datasets import ArmoryDataGenerator
from art.estimators import BaseEstimator

MethodName = Callable[
    ..., Any
]  # reference to a python method e.g. "armory.attacks.weakest"
StrDict = Dict[str, Any]  # dictionary of string keys and any values


@dataclass
class Attack:
    function: MethodName
    kwargs: StrDict
    knowledge: Literal["white", "black"]
    use_label: bool = False
    type: Optional[str] = None


@dataclass
class Dataset:
    name: str
    test_dataset: ArmoryDataGenerator
    train_dataset: Optional[ArmoryDataGenerator] = None


@dataclass
class Defense:
    function: MethodName
    kwargs: StrDict
    type: Literal[
        "Preprocessor",
        "Postprocessor",
        "Trainer",
        "Transformer",
        "PoisonFilteringDefense",
    ]


@dataclass
class Metric:
    profiler_type: Literal["basic", "deterministic"]
    supported_metrics: List[str]
    perturbation: List[str]
    task: List[str]
    means: bool
    record_metric_per_sample: bool


@dataclass
class Model:
    name: str
    model: BaseEstimator
    fit: bool = False
    fit_kwargs: StrDict = field(default_factory=dict)
    predict_kwargs: StrDict = field(default_factory=dict)


@dataclass
class Scenario:
    function: MethodName
    kwargs: StrDict


@dataclass
class SysConfig:
    # TODO: should get ArmoryControls (e.g. num_eval_batches, num_epochs, etc.)
    gpus: List[str]
    use_gpu: bool = False


@dataclass
class Evaluation:
    name: str
    description: str
    author: Optional[str]
    model: Model
    scenario: Scenario
    dataset: Dataset
    attack: Optional[Attack] = None
    defense: Optional[Defense] = None
    metric: Optional[Metric] = None
    sysconfig: Optional[SysConfig] = None


# List of old armory environmental variables used in evaluations
# self.config.update({
#   "ARMORY_GITHUB_TOKEN": os.getenv("ARMORY_GITHUB_TOKEN", default=""),
#   "ARMORY_PRIVATE_S3_ID": os.getenv("ARMORY_PRIVATE_S3_ID", default=""),
#   "ARMORY_PRIVATE_S3_KEY": os.getenv("ARMORY_PRIVATE_S3_KEY", default=""),
#   "ARMORY_INCLUDE_SUBMISSION_BUCKETS": os.getenv(
#     "ARMORY_INCLUDE_SUBMISSION_BUCKETS", default=""
#   ),
#   "VERIFY_SSL": self.armory_global_config["verify_ssl"] or False,
#   "NVIDIA_VISIBLE_DEVICES": self.config["sysconfig"].get("gpus", None),
#   "PYTHONHASHSEED": self.config["sysconfig"].get("set_pythonhashseed", "0"),
#   "TORCH_HOME": paths.HostPaths().pytorch_dir,
#   environment.ARMORY_VERSION: armory.__version__,
#   # "HOME": "/tmp",
# })
