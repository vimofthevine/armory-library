"""Utilities to load the VisDrone 2019 dataset."""

import csv
import io
from pathlib import Path
from pprint import pprint
from typing import Any, Dict, Iterator, List, Tuple

import datasets

import armory.data
import armory.dataset


def create_dataloader(
    dataset: datasets.Dataset, **kwargs
) -> armory.dataset.ObjectDetectionDataLoader:
    """
    Create an Armory object detection dataloader for the given VisDrone2019 dataset split.

    Args:
        dataset: VisDrone2019 dataset split
        **kwargs: Additional keyword arguments to pass to the dataloader constructor

    Return:
        Armory object detection dataloader
    """
    return armory.dataset.ObjectDetectionDataLoader(
        dataset,
        image_key="image",
        dim=armory.data.ImageDimensions.CHW,
        scale=armory.data.Scale(
            dtype=armory.data.DataType.UINT8,
            max=255,
        ),
        objects_key="objects",
        boxes_key="bbox",
        format=armory.data.BBoxFormat.XYWH,
        labels_key="category",
        **kwargs,
    )


GDRIVE_VAL_URL = "https://drive.usercontent.google.com/download?id=1bxK5zgLn0_L8x276eKkuYA_FzwCIjb59&confirm=1"
GDRIVE_TRAIN_URL = "https://drive.usercontent.google.com/download?id=1a2oHjcEcwXP8oUF95qiwrqzACb2YlUhn&confirm=1"


def load_dataset() -> datasets.DatasetDict:
    """
    Load the train and validation splits of the VisDrone2019 dataset.

    Return:
        Dictionary containing the train and validation splits
    """
    dl_manager = datasets.DownloadManager(dataset_name="VisDrone2019")
    ds_features = features()
    paths = dl_manager.download({"train": GDRIVE_TRAIN_URL, "val": GDRIVE_VAL_URL})
    train_files = dl_manager.iter_archive(paths["train"])
    val_files = dl_manager.iter_archive(paths["val"])
    return datasets.DatasetDict(
        {
            "train": datasets.Dataset.from_generator(
                generate_samples,
                gen_kwargs={"files": train_files},
                features=ds_features,
            ),
            "val": datasets.Dataset.from_generator(
                generate_samples,
                gen_kwargs={"files": val_files},
                features=ds_features,
            ),
        }
    )


CATEGORIES = [
    "ignored",
    "pedestrian",
    "people",
    "bicycle",
    "car",
    "van",
    "truck",
    "tricycle",
    "awning-tricycle",
    "bus",
    "motor",
    "other",
]


def features() -> datasets.Features:
    """Create VisDrone2019 dataset features"""
    return datasets.Features(
        {
            "image_id": datasets.Value("int64"),
            "file_name": datasets.Value("string"),
            "image": datasets.Image(),
            "objects": datasets.Sequence(
                {
                    "id": datasets.Value("int64"),
                    "bbox": datasets.Sequence(datasets.Value("float32"), length=4),
                    "category": datasets.ClassLabel(
                        num_classes=len(CATEGORIES), names=CATEGORIES
                    ),
                    "truncation": datasets.Value("int32"),
                    "occlusion": datasets.Value("int32"),
                }
            ),
        }
    )


ANNOTATION_FIELDS = [
    "x",
    "y",
    "width",
    "height",
    "score",
    "category_id",
    "truncation",
    "occlusion",
]


def load_annotations(file: io.BufferedReader) -> List[Dict[str, Any]]:
    """Load annotations/objects from the given file"""
    reader = csv.DictReader(
        io.StringIO(file.read().decode("utf-8")), fieldnames=ANNOTATION_FIELDS
    )
    annotations = []
    for idx, row in enumerate(reader):
        annotations.append(
            {
                "id": idx,
                "bbox": list(map(float, [row[k] for k in ANNOTATION_FIELDS[:4]])),
                "category": int(row["category_id"]),
                "truncation": row["truncation"],
                "occlusion": row["occlusion"],
            }
        )
    return annotations


def generate_samples(
    files: Iterator[Tuple[str, io.BufferedReader]], annotation_file_ext: str = ".txt"
) -> Iterator[Dict[str, Any]]:
    """Generate dataset samples from the given files in a VisDrone2019 archive"""
    image_to_annotations = {}
    # This loop relies on the ordering of the files in the archive:
    # Annotation files come first, then the images.
    for idx, (path, file) in enumerate(files):
        file_name = Path(path).stem
        if Path(path).suffix == annotation_file_ext:
            image_to_annotations[file_name] = load_annotations(file)
        elif file_name in image_to_annotations:
            yield {
                "image_id": idx,
                "file_name": file_name,
                "image": {"path": path, "bytes": file.read()},
                "objects": image_to_annotations[file_name],
            }
        else:
            raise ValueError(f"Image {file_name} has no annotations")


if __name__ == "__main__":
    pprint(load_dataset())
