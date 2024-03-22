from abc import ABC, abstractmethod
from typing import Callable, Iterable, Mapping, Optional, Union

from armory.data import Accessor, Batch, DefaultNumpyAccessor
from armory.export.sink import Sink


class Exporter(ABC):
    """Base class for an Armory sample exporter."""

    Criteria = Callable[[str, int, Batch], Union[bool, Iterable[int]]]

    def __init__(
        self,
        predictions_accessor: Optional[Accessor] = None,
        targets_accessor: Optional[Accessor] = None,
        criteria: Optional[Criteria] = None,
    ) -> None:
        """
        Initializes the exporter.

        Args:
            predictions_accessor: Optional, data exporter used to obtain
                low-level predictions data from the highly-structured
                predictions contained in exported batches. By default, a generic
                NumPy accessor is used.
            targets_accessor: Optional, data exporter used to obtain low-level
                ground truth targets data from the high-ly structured targets
                contained in exported batches. By default, a generic NumPy
                accessor is used.
            criteria: Criteria dictating when samples will be exported. If
                omitted, no samples will be exported.
        """
        self.predictions_accessor = predictions_accessor or DefaultNumpyAccessor()
        self.targets_accessor = targets_accessor or DefaultNumpyAccessor()
        self.sink: Optional[Sink] = None
        self.criteria = criteria

    def use_sink(self, sink: Sink) -> None:
        """Sets the export sink to be used by the exporter."""
        self.sink = sink

    def export(self, chain_name: str, batch_idx: int, batch: Batch) -> None:
        """
        Exports the given batch.

        Args:
            chain_name: The name of the perturbation chain from the evaluation
                to which this batch belongs.
            batch_idx: The index/number of this batch.
            batch: The batch to be exported.
        """
        assert self.sink, "No sink has been set, unable to export"
        if self.criteria is None:
            return
        to_export = self.criteria(chain_name, batch_idx, batch)
        if not to_export:
            return
        if type(to_export) is bool:
            # Because of the early-return above, to_export can only ever be True at this point
            to_export = range(len(batch))
        self.export_samples(chain_name, batch_idx, batch, to_export)

    @abstractmethod
    def export_samples(
        self, chain_name: str, batch_idx: int, batch: Batch, samples: Iterable[int]
    ) -> None:
        """
        Exports samples from the given batch.

        Args:
            chain_name: The name of the perturbation chain from the evaluation
                to which this batch belongs.
            batch_idx: The index/number of this batch.
            batch: The batch to be exported.
            samples: The indices of samples in the batch to be exported.
        """
        ...

    def _artifact_path(
        self, chain_name: str, batch_idx: int, sample_idx: int, filename: str
    ):
        return f"exports/{chain_name}/{batch_idx:05}/{sample_idx:02}/{filename}"

    @staticmethod
    def _from_list(maybe_list, idx):
        try:
            return maybe_list[idx]
        except:  # noqa: E722
            # if it's None or is not a list/sequence/etc, just return None
            return None

    def _export_metadata(
        self, chain_name: str, batch_idx: int, batch: Batch, samples: Iterable[int]
    ) -> None:
        assert self.sink, "No sink has been set, unable to export"

        targets = self.targets_accessor.get(batch.targets)
        predictions = self.predictions_accessor.get(batch.predictions)

        for sample_idx in samples:
            dictionary = dict(
                targets=self._from_list(targets, sample_idx),
                predictions=self._from_list(predictions, sample_idx),
            )
            for key, value in batch.metadata["data"].items():
                dictionary[key] = self._from_list(value, sample_idx)
            for perturbation, metadata in batch.metadata["perturbations"].items():
                if isinstance(metadata, Mapping):
                    dictionary.update(
                        {
                            f"{perturbation}.{k}": self._from_list(v, sample_idx)
                            for k, v in metadata.items()
                        }
                    )
                else:
                    dictionary[perturbation] = self._from_list(metadata, sample_idx)

            self.sink.log_dict(
                dictionary=dictionary,
                artifact_file=self._artifact_path(
                    chain_name, batch_idx, sample_idx, "metadata.txt"
                ),
            )
