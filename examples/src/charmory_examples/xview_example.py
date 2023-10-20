from pprint import pprint
import sys
import boto3
import botocore
from PIL import Image
import albumentations as A
import art.attacks.evasion
from art.estimators.object_detection import PyTorchFasterRCNN
from datasets import load_dataset
from jatic_toolbox import __version__ as jatic_version
from jatic_toolbox.interop.huggingface import HuggingFaceObjectDetectionDataset
from jatic_toolbox.interop.torchvision import TorchVisionObjectDetector
import numpy as np
import torch
from torchvision.transforms._presets import ObjectDetection

from armory.art_experimental.attacks.patch import AttackWrapper
from armory.metrics.compute import BasicProfiler
import armory.version
from charmory.data import ArmoryDataLoader, JaticObjectDetectionDataset
from charmory.engine import LightningEngine
from charmory.evaluation import Attack, Dataset, Evaluation, Metric, Model, SysConfig
from charmory.model.object_detection import JaticObjectDetectionModel
from charmory.tasks.object_detection import ObjectDetectionTask

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

from charmory.track import track_init_params
from charmory.utils import create_jatic_dataset_transform

BATCH_SIZE = 1
TRAINING_EPOCHS = 20
BUCKET_NAME = 'armory-library-data' 
KEY = 'fasterrcnn_mobilenet_v3_2' 
import torch

torch.set_float32_matmul_precision("high")
import armory.data.datasets


def load_huggingface_dataset():
    train_data = load_dataset("Honaker/xview_dataset_subset", split="train")

    new_dataset = train_data.train_test_split(test_size=0.4, seed=3)
    train_dataset, test_dataset = new_dataset["train"], new_dataset["test"]

    train_dataset, test_dataset = HuggingFaceObjectDetectionDataset(
        train_dataset
    ), HuggingFaceObjectDetectionDataset(test_dataset)

    return train_dataset, test_dataset


def main(argv: list = sys.argv[1:]):
    if len(argv) > 0:
        if "--version" in argv:
            print(f"armory: {armory.version.__version__}")
            print(f"JATIC-toolbox: {jatic_version}")
            sys.exit(0)

    print("Armory: Example Programmatic Entrypoint for Scenario Execution")
    ###
    # Model
    ###
    s3 = boto3.resource('s3')
    try:
        s3.Bucket(BUCKET_NAME).download_file(KEY, 'my_local_image.jpg')
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            print("The object does not exist.")
        else:
            raise

    
    model = torch.load(
        "/home/chris/armory/examples/src/charmory_examples/fasterrcnn_mobilenet_v3_2"
    )
    model.to(DEVICE)

    model = TorchVisionObjectDetector(
        model=model, processor=ObjectDetection(), labels=None
    )
    model.forward = model._model.forward

    detector = track_init_params(PyTorchFasterRCNN)(
        JaticObjectDetectionModel(model),
        channels_first=True,
        clip_values=(0.0, 1.0),
    )

    model_transform = create_jatic_dataset_transform(model.preprocessor)

    train_dataset, test_dataset = load_huggingface_dataset()

    img_transforms = A.Compose(
        [
            A.LongestMaxSize(max_size=500),
            A.PadIfNeeded(
                min_height=500,
                min_width=500,
                border_mode=0,
                value=(0, 0, 0),
            ),
        ],
        bbox_params=A.BboxParams(
            format="pascal_voc",
            label_fields=["labels"],
        ),
    )

    def transform(sample):
        transformed = dict(image=[], objects=[])
        for i in range(len(sample["image"])):
            transformed_img = img_transforms(
                image=np.asarray(sample["image"][i]),
                bboxes=sample["objects"][i]["bbox"],
                labels=sample["objects"][i]["category"],
            )
            transformed["image"].append(Image.fromarray(transformed_img["image"]))
            transformed["objects"].append(
                dict(
                    bbox=transformed_img["bboxes"],
                    category=transformed_img["labels"],
                )
            )
        transformed = model_transform(transformed)
        return transformed

    test_dataset.set_transform(transform)

    train_dataloader = ArmoryDataLoader(
        JaticObjectDetectionDataset(train_dataset),
        batch_size=BATCH_SIZE,
    )
    test_dataloader = ArmoryDataLoader(
        JaticObjectDetectionDataset(test_dataset),
        batch_size=BATCH_SIZE,
    )
    eval_dataset = Dataset(
        name="XVIEW",
        train_dataset=train_dataloader,
        test_dataset=test_dataloader,
    )
    eval_model = Model(
        name="xview-trained-fasterrcnn-resnet-50",
        model=detector,
    )

    patch = track_init_params(art.attacks.evasion.RobustDPatch)(
        detector,
        patch_shape=(3, 32, 32),
        batch_size=BATCH_SIZE,
        max_iter=20,
        targeted=False,
        verbose=False,
    )

    eval_attack = Attack(
        name="RobustDPatch",
        attack=AttackWrapper(patch),
        use_label_for_untargeted=False,
    )

    eval_metric = Metric(
        profiler=BasicProfiler(),
    )

    eval_sysconfig = SysConfig(
        gpus=["all"],
        use_gpu=True,
    )

    evaluation = Evaluation(
        name="xview-object-detection",
        description="XView object detection from HuggingFace",
        author="Chris Honaker",
        dataset=eval_dataset,
        model=eval_model,
        attack=eval_attack,
        metric=eval_metric,
        sysconfig=eval_sysconfig,
    )

    ###
    # Engine
    ###

    task = ObjectDetectionTask(
        evaluation,
        export_every_n_batches=2,
        class_metrics=False,
    )
    engine = LightningEngine(task, limit_test_batches=10)
    results = engine.run()

    pprint(results)


if __name__ == "__main__":
    sys.exit(main())
