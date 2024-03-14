"""
Example Armory evaluation of COCO object detection with Faster R-CNN with
ResNet-50 against a DPatch attack
"""

from pprint import pprint

import albumentations as A
import albumentations.pytorch.transforms
import art.attacks.evasion
import art.estimators.object_detection
import datasets
import numpy as np
import torch
import torchmetrics.detection
import torchvision.models.detection

import armory.data
import armory.dataset
import armory.engine
import armory.evaluation
import armory.export.criteria
import armory.export.object_detection
import armory.metric
import armory.metrics.compute
import armory.metrics.perturbation
import armory.model.object_detection
import armory.perturbation
import armory.track


def parse_cli_args():
    """Parse command-line arguments"""
    from armory.examples.utils.args import create_parser

    parser = create_parser(
        description="Perform COCO object detection with Faster R-CNN with ResNet-50",
        batch_size=4,
        export_every_n_batches=5,
        num_batches=20,
    )
    return parser.parse_args()


def load_model():
    tv_model = torchvision.models.detection.fasterrcnn_resnet50_fpn(
        torchvision.models.detection.FasterRCNN_ResNet50_FPN_Weights
    )

    armory_model = armory.model.object_detection.ObjectDetector(
        name="FasterRCNN-ResNet50",
        model=tv_model,
        inputs_accessor=armory.data.Images.as_torch(),
        predictions_accessor=armory.data.BoundingBoxes.as_torch(
            format=armory.data.BBoxFormat.XYXY
        ),
    )

    art_detector = armory.track.track_init_params(
        art.estimators.object_detection.PyTorchFasterRCNN
    )(
        tv_model,
        channels_first=True,
        input_shape=(3, 512, 512),
        clip_values=(0.0, 1.0),
    )

    return armory_model, art_detector


def load_dataset(batch_size: int, shuffle: bool):
    hf_dataset = datasets.load_dataset("rafaelpadilla/coco2017", split="val")
    assert isinstance(hf_dataset, datasets.Dataset)

    resize = A.Compose(
        [
            A.LongestMaxSize(512),
            A.PadIfNeeded(
                min_height=512,
                min_width=512,
                border_mode=0,
                value=(0, 0, 0),
            ),
            A.ToFloat(max_value=255),
            albumentations.pytorch.ToTensorV2(),
        ],
        bbox_params=A.BboxParams(
            format="coco",
            label_fields=["label", "id", "iscrowd"],
        ),
    )

    def transform(sample):
        tmp = dict(**sample)
        tmp["image"] = []
        tmp["objects"] = []
        for image, objects in zip(sample["image"], sample["objects"]):
            res = resize(
                image=np.asarray(image),
                bboxes=objects["bbox"],
                label=objects["label"],
                id=objects["id"],
                iscrowd=objects["iscrowd"],
            )
            tmp["image"].append(res.pop("image"))
            tmp["objects"].append(res)
        return tmp

    hf_dataset.set_transform(transform)

    dataloader = armory.dataset.ObjectDetectionDataLoader(
        hf_dataset,
        format=armory.data.BBoxFormat.XYWH,
        boxes_key="bboxes",
        dim=armory.data.ImageDimensions.CHW,
        scale=armory.data.Scale(dtype=armory.data.DataType.FLOAT, max=1.0),
        image_key="image",
        labels_key="label",
        objects_key="objects",
        batch_size=batch_size,
        shuffle=shuffle,
    )

    evaluation_dataset = armory.evaluation.Dataset(
        name="COCO 2017",
        dataloader=dataloader,
    )

    return evaluation_dataset


def create_attack(detector, batch_size: int = 1):
    dpatch = armory.track.track_init_params(art.attacks.evasion.RobustDPatch)(
        detector,
        patch_shape=(3, 50, 50),
        patch_location=(231, 231),  # middle of 512x512
        batch_size=batch_size,
        sample_size=10,
        learning_rate=0.01,
        max_iter=20,
        targeted=False,
        verbose=False,
    )

    evaluation_attack = armory.perturbation.ArtPatchAttack(
        name="RobustDPatch",
        attack=dpatch,
        use_label_for_untargeted=False,
        generate_every_batch=True,
    )

    return evaluation_attack


def create_metrics():
    return {
        "linf_norm": armory.metric.PerturbationMetric(
            armory.metrics.perturbation.PerturbationNormMetric(ord=torch.inf),
        ),
        "map": armory.metric.PredictionMetric(
            torchmetrics.detection.MeanAveragePrecision(class_metrics=False),
            armory.data.BoundingBoxes.as_torch(format=armory.data.BBoxFormat.XYXY),
        ),
    }


def create_exporters(export_every_n_batches):
    """Create sample exporters"""
    return [
        armory.export.object_detection.ObjectDetectionExporter(
            criteria=armory.export.criteria.every_n_batches(export_every_n_batches)
        ),
    ]


@armory.track.track_params(prefix="main")
def main(batch_size, export_every_n_batches, num_batches, seed, shuffle):
    """Perform evaluation"""
    if seed is not None:
        torch.manual_seed(seed)

    model, art_detector = load_model()

    dataset = load_dataset(batch_size, shuffle)
    attack = create_attack(art_detector, batch_size)
    metrics = create_metrics()
    exporters = create_exporters(export_every_n_batches)

    evaluation = armory.evaluation.Evaluation(
        name="coco-detection-fasterrcnn-resnet50",
        description="COCO object detection using Faster R-CNN with ResNet-50",
        author="TwoSix",
        dataset=dataset,
        model=model,
        perturbations={
            "benign": [],
            "attack": [attack],
        },
        metrics=metrics,
        exporters=exporters,
        profiler=armory.metrics.compute.BasicProfiler(),
    )

    engine = armory.engine.EvaluationEngine(
        evaluation,
        limit_test_batches=num_batches,
    )
    results = engine.run()

    pprint(results)


if __name__ == "__main__":
    main(**vars(parse_cli_args()))
