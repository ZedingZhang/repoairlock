from hello import greet


def test_greet_default() -> None:
    assert greet() == "Hello, World!"


def test_greet_name() -> None:
    assert greet("Alice") == "Hello, Alice!"
