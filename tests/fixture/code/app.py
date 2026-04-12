"""Tiny calculator module used as a test fixture for LyingDocs."""

DEFAULT_PRECISION = 2  # hardcoded; docs claim this is configurable via CALC_PRECISION


def add(a: int, b: int) -> int:
    """Return the integer sum of a and b."""
    return a + b


def multiply(a: int, b: int) -> int:
    return a * b


def main() -> None:
    print(add(2, 3))


if __name__ == "__main__":
    main()
