"""Matrix generation utilities"""

import concurrent.futures
from copy import deepcopy
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple


def product(
    prior: Dict[str, Any], remaining: List[Tuple[str, Any]]
) -> Iterable[Mapping[str, Any]]:
    """
    Generates a cartesian product of parameters.

    This function works recursively, iterating over each parameter range in a
    depth-first manner. We do this rather than use `itertools.product` in order
    to support dynamic, or dependent, parameter ranges that are created based
    on the preceding parameter values.

    Args:
        prior: Key-value parameter mapping of parameters generated so far
        remaining: List of remaining key and value-iterable pairs

    Yields:
        Key-value parameter mappings for each row in the cartesian product
        matrix
    """
    if not remaining:
        yield prior
    else:
        key, values = remaining[0]
        if callable(values):
            values = values(**prior)
        if not isinstance(values, Iterable):
            values = [values]
        for value in values:
            next = deepcopy(prior)
            next[key] = value
            for params in product(next, remaining[1:]):
                yield params


def create_matrix(
    worker_num: Optional[int] = None,
    num_workers: Optional[int] = None,
    prune: Optional[Callable[..., bool]] = None,
):
    """
    Creates a matrix of variable parameter values as a sequence of key-value
    argument mappings. The matrix is created as the cartesian product of all
    possible argument combinations.

    This function is not intended to be used directly, but is used internally
    by the `Matrix` class.

    Example::

        >>> from armory.matrix import create_matrix
        >>> list(create_matrix()(a=[1, 2], b=[3, 4]))
        [{'a': 1, 'b': 3}, {'a': 1, 'b': 4}, {'a': 2, 'b': 3}, {'a': 2, 'b': 4}]
        >>> list(create_matrix(1, 2)(a=[1, 2], b=[3, 4]))
        [{'a': 1, 'b': 4}, {'a': 2, 'b': 4}]
        >>> list(create_matrix(None, None, lambda a, b: a==2 and b==4)(a=[1, 2], b=[3, 4]))
        [{'a': 1, 'b': 3}, {'a': 1, 'b': 4}, {'a': 2, 'b': 3}]
        >>> list(create_matrix()(a=[1, 2], b=lambda a: (3, 4) if a == 1 else (5, 6)))
        [{'a': 1, 'b': 3}, {'a': 1, 'b': 4}, {'a': 2, 'b': 5}, {'a': 2, 'b': 6}]

    Args:
        worker_num: The index of this node among all nodes, used to determine
            which partition of the matrix to return. If specified, `num_workers`
            must also be provided.
        num_workers: The count of all nodes, used to determine the size of the
            partition of the matrix to return. If specified, `worker_num` must
            also be provided.
        prune: A callable to determine whether a row of the matrix should be
            pruned. If the callable returns `True` for a given set of
            parameters, that parameter set, or row, will be omitted from the
            returned matrix.

    Returns:
        A generator of key-value mappings. The generator function accepts
        keyword arguments of iterables, ranges, or sequences specifying the
        allowable values for each argument. The yielded value of the generator
        is a key-value mapping of arguments corresponding to a row of the
        matrix.

        If an argument to the generator is a callable, it will be called with
        the preceding keyword parameter values for the current row. The return
        of the callable is the value--or iterable--for the keyword, from which
        to generate additional rows in the matrix.
    """

    if worker_num is None or num_workers is None:
        worker_num = 0
        num_workers = 1

    def _generate(**kwargs) -> Iterable[Mapping[str, Any]]:
        count = 0
        for params in product({}, list(kwargs.items())):
            # Skip over entries that are pruned
            if prune is not None and prune(**params):
                continue
            # Skip over entries when partioning
            if (count % num_workers) == worker_num:
                yield params
            count += 1

    return _generate


class Matrix:
    """
    A function to be invoked multiple times with parameters from rows of a
    cartesian product matrix of all possible parameters.

    This class is not intended to be used directly, but is used internally by
    the `matrix` decorator.
    """

    def __init__(self, func: Callable, **kwargs):
        self.func = func
        self.kwargs = kwargs
        self.worker_num: Optional[int] = None
        self.num_workers: Optional[int] = None
        self.pruner: Optional[Callable[..., bool]] = None

    @property
    def matrix(self):
        """The generated matrix of arguments"""
        return create_matrix(
            worker_num=self.worker_num,
            num_workers=self.num_workers,
            prune=self.pruner,
        )(**self.kwargs)

    @property
    def num_rows(self):
        """Count of all rows in the matrix."""
        return sum(1 for _ in self.matrix)

    def __call__(self, *args, **kwargs):
        """
        Invokes the function once for each row of the matrix. Any given keyword
        arguments are merged with the keyword arguments from the matrix row.

        Args:
            *args: Positional arguments to be included with each function
                invocation
            **kwargs: Keyword arguments to be merged with the matrix row
                arguments for each function invocation

        Returns:
            List of return values from each function invocation
        """
        results = []
        for it in self.matrix:
            it_args = deepcopy(args)
            it_kwargs = deepcopy(kwargs)
            it_kwargs.update(it)
            try:
                results.append(self.func(*it_args, **it_kwargs))
            except Exception as err:
                results.append(err)
        return results

    def override(self, **kwargs):
        """Overrides the input parameter constraints for the matrix."""
        self.kwargs.update(kwargs)
        return self

    def partition(self, worker_num: Optional[int], num_workers: Optional[int]):
        """
        Specifies the worker index and count used to partition the matrix for
        parallel-worker applications.
        """
        self.worker_num = worker_num
        self.num_workers = num_workers
        return self

    def prune(self, pruner: Optional[Callable[..., bool]]):
        """Specifies the pruner callable to be used when generating the matrix."""
        self.pruner = pruner
        return self

    def parallel(self, max_workers):
        """
        Creates a thread pool in which to perform the invoked function for each
        row of the matrix.

        Example::

            @matrix(x=[1, 2], y=[3, 4])
            def perform(x, y):
                return x * y

            perform.parallel(2)()  # Will use up to 2 threads

        Args:
            Maximum number of workers to use in the thread pool

        Returns:
            A function that will accept additional arguments to be forwarded to
            the invoked function and execute all rows of the matrix within the
            thread pool. The return of the function will be a list of all return
            values from each invocation of the matrix rows.
        """
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

        def _run(*args, **kwargs):
            futures = []
            for it in self.matrix:
                it_args = deepcopy(args)
                it_kwargs = deepcopy(kwargs)
                it_kwargs.update(it)
                futures.append(executor.submit(self.func, *it_args, **it_kwargs))

            results = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as err:
                    results.append(err)
            return results

        return _run


def matrix(**kwargs):
    """
    Create a decorator to invoke the wrapped function once for each row of the
    parameter matrix created by the cartesian product of all input parameter
    values.

    Example::

        >>> from armory.matrix import matrix

        >>> @matrix(x=range(5))
        ... def perform(a, x, b):
        ...    return (a * x) + b

        >>> perform(2, b=3)
        [3, 5, 7, 9, 11]

        >>> # to filter by pruning...
        >>> perform.prune(lambda x: x % 2 == 1)(2, b=3)
        [3, 7, 11]
        >>> # Use None to clear pruning
        >>> perform.prune(None)(2, b=3)
        [3, 5, 7, 9, 11]

        >>> # to partition
        >>> perform.partition(0, 2)(2, b=3)
        [3, 7, 11]
        >>> perform.partition(1, 2)(2, b=3)
        [5, 9]
        >>> # Use None to clear partition
        >>> perform.partition(None, None)(2, b=3)
        [3, 5, 7, 9, 11]

        >>> # to override arguments
        >>> perform.override(x=range(3, 7))(2, b=3)
        [9, 11, 13, 15]

    Args:
        **kwargs: Keyword arguments to produce the parameter matrix. Argument
            values should be iterables (e.g., generator, list) of the allowable
            values for their respective named argument.

    Returns:
        Function decorator to wrap a given function in a callable `Matrix` object.
    """

    def decorator(func):
        return Matrix(func, **kwargs)

    return decorator
