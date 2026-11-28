"""Every GraphQL document the collector sends. Page sizes are kept small enough that one search page stays well
under GitHub's node limit (500 000) and costs about a dozen rate-limit points. A history page of COMMIT_PAGE commits
with COMMIT_AUTHORS authors each is at most about 1 200 nodes and costs 2 to 3 points."""
from __future__ import annotations

COMMIT_PAGE = 100           # commits per history page
COMMIT_AUTHORS = 10         # authors per commit: the primary author, then the `Co-authored-by:` trailers
SEARCH_PAGE = 25            # pull requests per search page
NESTED_PAGE = 50            # reviews and conversation comments inlined per pull request
THREAD_PAGE = 30            # review threads per pull request, and comments per thread, inlined
FOLLOW_UP_PAGE = 100        # page size of the node(id:) follow-ups

_RATE = "rateLimit { remaining resetAt }"
_PAGE_INFO = "pageInfo { hasNextPage endCursor }"
_ACTOR = "author { login __typename }"

COMMITS = """query($owner: String!, $name: String!, $since: GitTimestamp, $until: GitTimestamp, $after: String,
  $first: Int!) {
  %(rate)s
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: $first, after: $after, since: $since, until: $until) {
        %(page)s
        nodes {
          oid committedDate authoredDate additions deletions changedFilesIfAvailable
          parents { totalCount }
          author { name email user { login __typename } }
          authors(first: %(authors)s) { nodes { name email user { login __typename } } }
          associatedPullRequests(first: 1) { nodes { number } }
        }
      }
    } } }
  }
}""" % {"rate": _RATE, "page": _PAGE_INFO, "authors": COMMIT_AUTHORS}

_REVIEW = f"fragment Review on PullRequestReview {{ databaseId state submittedAt {_ACTOR} }}"
_COMMENT = f"fragment Comment on IssueComment {{ databaseId createdAt {_ACTOR} }}"
_REVIEW_COMMENT = (f"fragment ReviewComment on PullRequestReviewComment {{ databaseId createdAt {_ACTOR} "
                   f"replyTo {{ databaseId }} }}")
_THREAD = (f"fragment Thread on PullRequestReviewThread {{ id comments(first: {THREAD_PAGE}) {{ totalCount "
           f"{_PAGE_INFO} nodes {{ ...ReviewComment }} }} }}")

SEARCH_PULL_REQUESTS = f"""query($q: String!, $after: String, $first: Int!) {{
  {_RATE}
  search(query: $q, type: ISSUE, first: $first, after: $after) {{
    issueCount
    {_PAGE_INFO}
    nodes {{ ... on PullRequest {{
      id number createdAt mergedAt closedAt state baseRefName isDraft changedFiles additions deletions
      {_ACTOR}
      labels(first: 20) {{ nodes {{ name }} }}
      commits {{ totalCount }}
      reviews(first: {NESTED_PAGE}) {{ totalCount {_PAGE_INFO} nodes {{ ...Review }} }}
      comments(first: {NESTED_PAGE}) {{ totalCount {_PAGE_INFO} nodes {{ ...Comment }} }}
      reviewThreads(first: {THREAD_PAGE}) {{ {_PAGE_INFO} nodes {{ ...Thread }} }}
    }} }}
  }}
}}
{_REVIEW}
{_COMMENT}
{_THREAD}
{_REVIEW_COMMENT}"""


def _follow_up(on: str, connection: str, nodes: str, *fragments: str) -> str:
    return "\n".join([f"""query($id: ID!, $after: String, $first: Int!) {{
  {_RATE}
  node(id: $id) {{ ... on {on} {{
    {connection}(first: $first, after: $after) {{ {_PAGE_INFO} nodes {{ {nodes} }} }}
  }} }}
}}""", *fragments])


PR_REVIEWS = _follow_up("PullRequest", "reviews", "...Review", _REVIEW)
PR_COMMENTS = _follow_up("PullRequest", "comments", "...Comment", _COMMENT)
PR_THREADS = _follow_up("PullRequest", "reviewThreads", "...Thread", _THREAD, _REVIEW_COMMENT)
THREAD_COMMENTS = _follow_up("PullRequestReviewThread", "comments", "...ReviewComment", _REVIEW_COMMENT)
