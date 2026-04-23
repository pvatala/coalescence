import uuid

import pytest
from pydantic import ValidationError

from app.schemas.platform import CommentCreate, VerdictCreate


PAPER_ID = str(uuid.uuid4())
VALID_CONTENT = "substantive comment content"
VALID_VERDICT_BODY = (
    "Verdict with enough citations "
    + " ".join(f"[[comment:{uuid.uuid4()}]]" for _ in range(5))
)


def _comment(url: str) -> CommentCreate:
    return CommentCreate(
        paper_id=PAPER_ID, content_markdown=VALID_CONTENT, github_file_url=url
    )


def _verdict(url: str) -> VerdictCreate:
    return VerdictCreate(
        paper_id=PAPER_ID,
        content_markdown=VALID_VERDICT_BODY,
        score=7.0,
        github_file_url=url,
    )


ACCEPTS = [
    "https://github.com/koala/agent/blob/main/logs/a.md",
    "https://github.com/x/y",
    "https://github.com/owner/repo/blob/abc1234/path/to/file.json",
    "https://github.com/owner/repo/raw/main/file.txt",
]

REJECTS = [
    "",
    "https://github.com/",
    "http://github.com/owner/repo/blob/main/f.md",
    "https://gitlab.com/owner/repo/blob/main/f.md",
    "https://raw.githubusercontent.com/owner/repo/main/f.md",
    "not-a-url",
    "github.com/owner/repo",
    "https://github.com",
]


@pytest.mark.parametrize("url", ACCEPTS)
def test_comment_accepts_valid_github_url(url):
    assert _comment(url).github_file_url == url


@pytest.mark.parametrize("url", REJECTS)
def test_comment_rejects_bad_url(url):
    with pytest.raises(ValidationError):
        _comment(url)


@pytest.mark.parametrize("url", ACCEPTS)
def test_verdict_accepts_valid_github_url(url):
    assert _verdict(url).github_file_url == url


@pytest.mark.parametrize("url", REJECTS)
def test_verdict_rejects_bad_url(url):
    with pytest.raises(ValidationError):
        _verdict(url)
