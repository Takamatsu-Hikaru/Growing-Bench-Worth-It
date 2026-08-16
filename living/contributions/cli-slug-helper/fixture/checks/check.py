from src.commands import create_target


def main() -> None:
    expected = {
        "  My Demo  ": "targets/my-demo",
        "Release___Candidate": "targets/release-candidate",
        "Paper / Review": "targets/paper-review",
    }
    for label, target in expected.items():
        actual = create_target(label)
        if actual != target:
            raise AssertionError(f"{label!r}: expected {target!r}, got {actual!r}")
    print("focused check passed")


if __name__ == "__main__":
    main()
