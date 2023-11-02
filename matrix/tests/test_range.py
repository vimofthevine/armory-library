from armory_matrix.range import frange
import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "start,stop,step,expected",
    [
        (5, None, None, [0.0, 1.0, 2.0, 3.0, 4.0]),
        (5, None, 0.5, [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5]),
        (2, 5, None, [2.0, 3.0, 4.0]),
        (2, 5, 0.5, [2.0, 2.5, 3.0, 3.5, 4.0, 4.5]),
        (5, 2, -0.5, [5.0, 4.5, 4.0, 3.5, 3.0, 2.5]),
        (1.5, 2.0, 0.1, [1.5, 1.6, 1.7, 1.8, 1.9]),
    ],
)
def test_frange(start, stop, step, expected):
    assert list(frange(start, stop, step)) == expected
