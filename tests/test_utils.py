import pytest

from gitpulse.utils import UserError, parse_events, parse_repo


@pytest.mark.parametrize(
    "value, expected",
    [
        ("saiyii/gitpulse", "saiyii/gitpulse"),
        ("  saiyii/gitpulse ", "saiyii/gitpulse"),
        ("octocat/octocat.github.io", "octocat/octocat.github.io"),
        ("https://github.com/saiyii/gitpulse", "saiyii/gitpulse"),
        ("github.com/saiyii/gitpulse/", "saiyii/gitpulse"),
        ("https://github.com/saiyii/gitpulse.git", "saiyii/gitpulse"),
        ("https://github.com/saiyii/gitpulse/issues/12", "saiyii/gitpulse"),
    ],
)
def test_parse_repo(value, expected):
    assert parse_repo(value) == expected


@pytest.mark.parametrize("value", ["", "gitpulse", "saiyii/", "-bad/repo", "a b/c", "owner/.."])
def test_parse_repo_rejects(value):
    with pytest.raises(UserError):
        parse_repo(value)


def test_parse_events():
    assert parse_events(None) == {"releases"}
    assert parse_events("push, issues") == {"push", "issues"}
    assert parse_events("release prs") == {"releases", "pulls"}
    assert parse_events("all") == {"releases", "push", "issues", "pulls"}
    with pytest.raises(UserError):
        parse_events("stars")
