import copy
import json
from pathlib import Path

import pytest

from gitpulse import embeds
from gitpulse.embeds import (
    Color,
    build_embed,
    excerpt,
    release_embed,
    should_announce_push,
    truncate,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def check_limits(embed) -> None:
    assert len(embed) <= embeds.TOTAL_LIMIT
    assert len(embed.title or "") <= embeds.TITLE_LIMIT
    assert len(embed.description or "") <= embeds.DESCRIPTION_LIMIT
    assert len(embed.fields) <= embeds.MAX_FIELDS
    for field in embed.fields:
        assert len(field.value) <= embeds.FIELD_VALUE_LIMIT


@pytest.mark.parametrize(
    "event, fixture",
    [
        ("release", "release_published"),
        ("push", "push"),
        ("issues", "issues_opened"),
        ("issues", "issues_closed"),
        ("pull_request", "pull_request_merged"),
    ],
)
def test_fixtures_build_valid_embeds(event, fixture):
    embed = build_embed(event, load(fixture))
    assert embed is not None
    check_limits(embed)
    assert embed.footer.icon_url == embeds.GITHUB_ICON


# -- helpers ----------------------------------------------------------------


def test_truncate():
    assert truncate("short", 10) == "short"
    assert truncate("a" * 20, 10) == "a" * 9 + "…"
    assert len(truncate("a" * 5000, 4096)) == 4096


def test_excerpt_strips_html_comments():
    assert excerpt("<!-- hidden -->\r\nvisible", 100) == "visible"


def test_excerpt_closes_code_fence():
    text = "intro\n```py\n" + "print('x')\n" * 200 + "```"
    short = excerpt(text, 300, "https://example.com")
    assert short.count("```") % 2 == 0
    assert short.endswith("[Read more](https://example.com)")
    assert len(short) <= 300


# -- releases ---------------------------------------------------------------


def test_release_embed():
    embed = build_embed("release", load("release_published"))
    assert embed.title == "saiyii/nuclear-resource v2.3.0"
    assert embed.url == "https://github.com/saiyii/nuclear-resource/releases/tag/v2.3.0"
    assert embed.color.value == Color.RELEASE
    assert embed.author.name == "saiyii"
    assert "<!--" not in embed.description
    assert "Fix false positive on vehicle spawn" in embed.description

    fields = {f.name: f.value for f in embed.fields}
    assert fields["Tag"] == "`v2.3.0`"
    assert "nuclear-resource-v2.3.0.zip" in fields["Assets (2)"]
    assert "1.8 MB" in fields["Assets (2)"]


def test_release_long_notes_get_read_more_link():
    payload = load("release_published")
    payload["release"]["body"] = "\n".join(f"* change number {i}" for i in range(2000))
    embed = build_embed("release", payload)
    assert len(embed.description) <= embeds.RELEASE_NOTES_LIMIT
    assert embed.description.endswith(f"[Read more]({payload['release']['html_url']})")
    check_limits(embed)


def test_release_many_assets():
    release = load("release_published")["release"]
    asset = release["assets"][0]
    release["assets"] = [dict(asset, name=f"build-{i}.zip") for i in range(30)]
    embed = release_embed("saiyii/nuclear-resource", release)
    value = embed.fields[-1].value
    assert value.count("build-") == embeds.MAX_ASSETS
    assert value.endswith("+25 more")


def test_prerelease_color():
    payload = load("release_published")
    payload["release"]["prerelease"] = True
    embed = build_embed("release", payload)
    assert embed.color.value == Color.PRERELEASE


@pytest.mark.parametrize("action", ["created", "edited", "deleted", "prereleased"])
def test_release_other_actions_ignored(action):
    payload = load("release_published")
    payload["action"] = action
    assert build_embed("release", payload) is None


def test_release_without_notes_or_assets():
    release = load("release_published")["release"]
    release["body"] = None
    release["assets"] = []
    embed = release_embed("saiyii/nuclear-resource", release)
    assert embed.description == "*No release notes.*"
    assert embed.fields[-1].name == "Source code"


# -- pushes -----------------------------------------------------------------


def test_push_embed():
    embed = build_embed("push", load("push"))
    assert embed.title == "[saiyii/gitpulse:main] 7 new commits"
    assert embed.color.value == Color.PUSH

    lines = embed.description.splitlines()
    assert len(lines) == 6
    assert lines[0].startswith("[`a1b2c3d`](https://github.com/saiyii/gitpulse/commit/a1b2c3d")
    # only the first line of the commit message
    assert "Shows tag" not in embed.description
    # markdown in messages is escaped
    assert "\\*markdown\\*" in lines[2]
    # falls back to the git author name when there is no GitHub user
    assert lines[2].endswith("Some Contributor")
    assert lines[-1] == "+2 more"


def test_push_single_commit():
    payload = load("push")
    payload["commits"] = payload["commits"][:1]
    embed = build_embed("push", payload)
    assert embed.title.endswith("1 new commit")


def test_push_filters():
    payload = load("push")
    assert should_announce_push(payload)

    other = copy.deepcopy(payload)
    other["ref"] = "refs/heads/feature/x"
    assert not should_announce_push(other)
    assert should_announce_push(other, all_branches=True)

    tag = copy.deepcopy(payload)
    tag["ref"] = "refs/tags/v1.0.0"
    assert not should_announce_push(tag, all_branches=True)
    assert build_embed("push", tag) is None

    deleted = copy.deepcopy(payload)
    deleted["deleted"] = True
    deleted["commits"] = []
    assert not should_announce_push(deleted)
    assert build_embed("push", deleted) is None


def test_force_push_is_flagged():
    payload = load("push")
    payload["forced"] = True
    embed = build_embed("push", payload)
    assert embed.description.startswith("**Force-pushed**")


# -- issues and pull requests -----------------------------------------------


def test_issue_opened():
    embed = build_embed("issues", load("issues_opened"))
    assert embed.title == (
        "[saiyii/gitpulse] Issue opened: #12 /repo fails on repositories with a dot in the name"
    )
    assert embed.color.value == Color.OPEN
    assert "Steps:" in embed.description
    assert embed.fields[0].value == "`bug` `good first issue`"


def test_issue_closed_not_planned():
    embed = build_embed("issues", load("issues_closed"))
    assert "closed as not planned" in embed.title
    assert embed.color.value == Color.MUTED
    assert embed.description is None


@pytest.mark.parametrize("action", ["labeled", "assigned", "edited"])
def test_issue_other_actions_ignored(action):
    payload = load("issues_opened")
    payload["action"] = action
    assert build_embed("issues", payload) is None


def test_pull_request_merged():
    embed = build_embed("pull_request", load("pull_request_merged"))
    assert (
        embed.title == "[saiyii/gitpulse] Pull request merged: #14 Allow dots in repository names"
    )
    assert embed.color.value == Color.DONE
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Branches"] == "`fix/repo-name-regex` → `main`"
    assert fields["Changes"] == "+12 / -3 in 2 files"


def test_pull_request_closed_without_merge():
    payload = load("pull_request_merged")
    payload["pull_request"].update(merged=False, merged_at=None)
    embed = build_embed("pull_request", payload)
    assert "Pull request closed" in embed.title
    assert embed.color.value == Color.CLOSED


def test_pull_request_opened_draft():
    payload = load("pull_request_merged")
    payload["action"] = "opened"
    payload["pull_request"].update(
        state="open", merged=False, merged_at=None, closed_at=None, draft=True
    )
    embed = build_embed("pull_request", payload)
    assert "opened as draft" in embed.title
    assert embed.color.value == Color.MUTED
    assert embed.description == "Fixes #12"


def test_long_issue_title_is_truncated():
    payload = load("issues_opened")
    payload["issue"]["title"] = "x" * 500
    embed = build_embed("issues", payload)
    check_limits(embed)


def test_unknown_event():
    assert build_embed("star", {"action": "created"}) is None
