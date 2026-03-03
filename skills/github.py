"""GitHub utilities backed by GitHub REST API."""

from __future__ import annotations

import os
from typing import Any

import requests
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

try:
	from dotenv import load_dotenv

	load_dotenv()
except Exception:
	pass


class GitHubError(RuntimeError):
	"""Raised when GitHub API operations fail."""


def _require_env(name: str) -> str:
	value = os.environ.get(name, "").strip()
	if not value:
		raise GitHubError(f"Missing required environment variable: {name}")
	return value


def _get_headers() -> dict[str, str]:
	"""Get common headers for GitHub API requests."""
	token = _require_env("GITHUB_TOKEN")
	return {
		"Authorization": f"Bearer {token}",
		"Accept": "application/vnd.github+json",
		"X-GitHub-Api-Version": "2022-11-28",
	}



async def get_repository(
	ctx: Context[ServerSession, None],
	owner: str,
	repo: str,
) -> dict[str, Any]:
	"""Get detailed information about a GitHub repository.

	Args:
		owner: Repository owner (username or organization).
		repo: Repository name.

	Returns:
		Dictionary with repository information including name, description,
		stars, forks, language, etc.
	"""
	url = f"https://api.github.com/repos/{owner}/{repo}"
	
	try:
		response = requests.get(url, headers=_get_headers(), timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to get repository: {exc}") from exc

	data = response.json()
	result = {
		"name": data.get("name"),
		"full_name": data.get("full_name"),
		"description": data.get("description"),
		"url": data.get("html_url"),
		"stars": data.get("stargazers_count"),
		"forks": data.get("forks_count"),
		"watchers": data.get("watchers_count"),
		"language": data.get("language"),
		"open_issues": data.get("open_issues_count"),
		"created_at": data.get("created_at"),
		"updated_at": data.get("updated_at"),
		"default_branch": data.get("default_branch"),
		"is_private": data.get("private"),
		"topics": data.get("topics", []),
	}

	await ctx.info(f"Retrieved information for {owner}/{repo}")
	return result



async def create_repository(
	ctx: Context[ServerSession, None],
	name: str,
	description: str = "",
	private: bool = False,
	auto_init: bool = True,
) -> dict[str, Any]:
	"""Create a new GitHub repository in the authenticated user's account.

	Args:
		name: Repository name.
		description: Repository description.
		private: Whether the repository should be private. Defaults to False.
		auto_init: Initialize with README. Defaults to True.

	Returns:
		Dictionary with the created repository information.
	"""
	url = "https://api.github.com/user/repos"
	payload = {
		"name": name,
		"description": description,
		"private": private,
		"auto_init": auto_init,
	}

	try:
		response = requests.post(url, headers=_get_headers(), json=payload, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to create repository: {exc}") from exc

	data = response.json()
	result = {
		"name": data.get("name"),
		"full_name": data.get("full_name"),
		"url": data.get("html_url"),
		"clone_url": data.get("clone_url"),
		"ssh_url": data.get("ssh_url"),
	}

	await ctx.info(f"Created repository: {data.get('full_name')}")
	return result



async def list_issues(
	ctx: Context[ServerSession, None],
	owner: str,
	repo: str,
	state: str = "open",
	max_results: int = 10,
) -> dict[str, Any]:
	"""List issues for a GitHub repository.

	Args:
		owner: Repository owner.
		repo: Repository name.
		state: Issue state - 'open', 'closed', or 'all'. Defaults to 'open'.
		max_results: Maximum number of issues to return. Defaults to 10.

	Returns:
		Dictionary with list of issues.
	"""
	url = f"https://api.github.com/repos/{owner}/{repo}/issues"
	params = {
		"state": state,
		"per_page": min(max_results, 100),
	}

	try:
		response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to list issues: {exc}") from exc

	data = response.json()
	issues = []
	for item in data:
		# Skip pull requests (they also appear in issues endpoint)
		if "pull_request" in item:
			continue
		issues.append({
			"number": item.get("number"),
			"title": item.get("title"),
			"state": item.get("state"),
			"url": item.get("html_url"),
			"created_at": item.get("created_at"),
			"updated_at": item.get("updated_at"),
			"author": item.get("user", {}).get("login"),
			"labels": [label.get("name") for label in item.get("labels", [])],
			"comments": item.get("comments"),
		})

	await ctx.info(f"Retrieved {len(issues)} issues from {owner}/{repo}")
	return {
		"repository": f"{owner}/{repo}",
		"state": state,
		"count": len(issues),
		"issues": issues,
	}



async def create_issue(
	ctx: Context[ServerSession, None],
	owner: str,
	repo: str,
	title: str,
	body: str = "",
	labels: list[str] | None = None,
) -> dict[str, Any]:
	"""Create a new issue in a GitHub repository.

	Args:
		owner: Repository owner.
		repo: Repository name.
		title: Issue title.
		body: Issue body/description.
		labels: List of label names to apply.

	Returns:
		Dictionary with the created issue information.
	"""
	url = f"https://api.github.com/repos/{owner}/{repo}/issues"
	payload = {
		"title": title,
		"body": body,
	}
	if labels:
		payload["labels"] = labels

	try:
		response = requests.post(url, headers=_get_headers(), json=payload, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to create issue: {exc}") from exc

	data = response.json()
	result = {
		"number": data.get("number"),
		"title": data.get("title"),
		"url": data.get("html_url"),
		"state": data.get("state"),
		"created_at": data.get("created_at"),
	}

	await ctx.info(f"Created issue #{data.get('number')} in {owner}/{repo}")
	return result



async def list_pull_requests(
	ctx: Context[ServerSession, None],
	owner: str,
	repo: str,
	state: str = "open",
	max_results: int = 10,
) -> dict[str, Any]:
	"""List pull requests for a GitHub repository.

	Args:
		owner: Repository owner.
		repo: Repository name.
		state: PR state - 'open', 'closed', or 'all'. Defaults to 'open'.
		max_results: Maximum number of PRs to return. Defaults to 10.

	Returns:
		Dictionary with list of pull requests.
	"""
	url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
	params = {
		"state": state,
		"per_page": min(max_results, 100),
	}

	try:
		response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to list pull requests: {exc}") from exc

	data = response.json()
	prs = []
	for item in data:
		prs.append({
			"number": item.get("number"),
			"title": item.get("title"),
			"state": item.get("state"),
			"url": item.get("html_url"),
			"created_at": item.get("created_at"),
			"updated_at": item.get("updated_at"),
			"author": item.get("user", {}).get("login"),
			"head_branch": item.get("head", {}).get("ref"),
			"base_branch": item.get("base", {}).get("ref"),
			"mergeable": item.get("mergeable"),
			"merged": item.get("merged"),
		})

	await ctx.info(f"Retrieved {len(prs)} pull requests from {owner}/{repo}")
	return {
		"repository": f"{owner}/{repo}",
		"state": state,
		"count": len(prs),
		"pull_requests": prs,
	}



async def create_pull_request(
	ctx: Context[ServerSession, None],
	owner: str,
	repo: str,
	title: str,
	head: str,
	base: str,
	body: str = "",
) -> dict[str, Any]:
	"""Create a new pull request in a GitHub repository.

	Args:
		owner: Repository owner.
		repo: Repository name.
		title: PR title.
		head: The name of the branch where your changes are implemented.
		base: The name of the branch you want the changes pulled into.
		body: PR description.

	Returns:
		Dictionary with the created pull request information.
	"""
	url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
	payload = {
		"title": title,
		"head": head,
		"base": base,
		"body": body,
	}

	try:
		response = requests.post(url, headers=_get_headers(), json=payload, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to create pull request: {exc}") from exc

	data = response.json()
	result = {
		"number": data.get("number"),
		"title": data.get("title"),
		"url": data.get("html_url"),
		"state": data.get("state"),
		"created_at": data.get("created_at"),
		"head_branch": data.get("head", {}).get("ref"),
		"base_branch": data.get("base", {}).get("ref"),
	}

	await ctx.info(f"Created pull request #{data.get('number')} in {owner}/{repo}")
	return result



async def list_repositories(
	ctx: Context[ServerSession, None],
	username: str = "",
	max_results: int = 10,
) -> dict[str, Any]:
	"""List repositories for a GitHub user or the authenticated user.

	Args:
		username: GitHub username. If empty, lists repos for authenticated user.
		max_results: Maximum number of repositories to return. Defaults to 10.

	Returns:
		Dictionary containing repository list and metadata.
	"""
	# Choose correct endpoint depending on whether a username is supplied
	if username:
		url = f"https://api.github.com/users/{username}/repos"
	else:
		url = "https://api.github.com/user/repos"

	params = {"per_page": min(max_results, 100)}

	try:
		response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to list repositories: {exc}") from exc

	data = response.json()
	repos = []
	for item in data:
		repos.append({
			"name": item.get("name"),
			"full_name": item.get("full_name"),
			"description": item.get("description"),
			"url": item.get("html_url"),
			"stars": item.get("stargazers_count"),
			"forks": item.get("forks_count"),
			"language": item.get("language"),
			"private": item.get("private"),
		})

	user = username if username else "authenticated user"
	await ctx.info(f"Retrieved {len(repos)} repositories for {user}")
	return {
		"user": username or "authenticated",
		"count": len(repos),
		"repositories": repos,
	}


async def get_user(
	ctx: Context[ServerSession, None],
	username: str = "",
) -> dict[str, Any]:
	"""Get information about a GitHub user.

	Args:
		username: GitHub username. If empty, returns authenticated user info.

	Returns:
		Dictionary with user information.
	"""
	url = f"https://api.github.com/users/{username}" if username else "https://api.github.com/user"

	try:
		response = requests.get(url, headers=_get_headers(), timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to get user information: {exc}") from exc

	data = response.json()
	result = {
		"username": data.get("login"),
		"name": data.get("name"),
		"bio": data.get("bio"),
		"url": data.get("html_url"),
		"avatar_url": data.get("avatar_url"),
		"followers": data.get("followers"),
		"following": data.get("following"),
		"public_repos": data.get("public_repos"),
		"created_at": data.get("created_at"),
		"company": data.get("company"),
		"location": data.get("location"),
		"blog": data.get("blog"),
	}

	await ctx.info(f"Retrieved information for user: {data.get('login')}")
	return result



async def search_repositories(
	ctx: Context[ServerSession, None],
	query: str,
	sort: str = "stars",
	max_results: int = 10,
) -> dict[str, Any]:
	"""Search for GitHub repositories.

	Args:
		query: Search query (e.g., 'language:python topic:ai').
		sort: Sort by 'stars', 'forks', or 'updated'. Defaults to 'stars'.
		max_results: Maximum number of results. Defaults to 10.

	Returns:
		Dictionary with search results.
	"""
	url = "https://api.github.com/search/repositories"
	params = {
		"q": query,
		"sort": sort,
		"per_page": min(max_results, 100),
	}

	try:
		response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to search repositories: {exc}") from exc

	data = response.json()
	repositories = []
	for item in data.get("items", []):
		repositories.append({
			"name": item.get("name"),
			"full_name": item.get("full_name"),
			"description": item.get("description"),
			"url": item.get("html_url"),
			"stars": item.get("stargazers_count"),
			"forks": item.get("forks_count"),
			"language": item.get("language"),
			"updated_at": item.get("updated_at"),
		})

	await ctx.info(f"Found {len(repositories)} repositories matching '{query}'")
	return {
		"query": query,
		"total_count": data.get("total_count"),
		"count": len(repositories),
		"repositories": repositories,
	}



async def get_file_contents(
	ctx: Context[ServerSession, None],
	owner: str,
	repo: str,
	path: str,
	ref: str = "",
) -> dict[str, Any]:
	"""Get the contents of a file from a GitHub repository.

	Args:
		owner: Repository owner.
		repo: Repository name.
		path: Path to the file in the repository.
		ref: Branch, tag, or commit SHA. Defaults to default branch.

	Returns:
		Dictionary with file information and contents.
	"""
	url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
	params = {}
	if ref:
		params["ref"] = ref

	try:
		response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to get file contents: {exc}") from exc

	data = response.json()
	
	# Decode base64 content
	import base64
	content = ""
	if data.get("encoding") == "base64" and data.get("content"):
		try:
			content = base64.b64decode(data.get("content")).decode("utf-8")
		except Exception:
			content = "[Binary file or encoding error]"

	result = {
		"name": data.get("name"),
		"path": data.get("path"),
		"size": data.get("size"),
		"url": data.get("html_url"),
		"download_url": data.get("download_url"),
		"content": content,
		"sha": data.get("sha"),
	}

	await ctx.info(f"Retrieved file {path} from {owner}/{repo}")
	return result



async def create_branch(
	ctx: Context[ServerSession, None],
	owner: str,
	repo: str,
	branch_name: str,
	from_branch: str = "",
) -> dict[str, Any]:
	"""Create a new branch in a GitHub repository.

	Args:
		owner: Repository owner.
		repo: Repository name.
		branch_name: Name for the new branch.
		from_branch: Branch to create from. Defaults to default branch.

	Returns:
		Dictionary with the created branch information.
	"""
	# First, get the SHA of the branch to create from
	if not from_branch:
		# Get default branch
		repo_url = f"https://api.github.com/repos/{owner}/{repo}"
		try:
			repo_response = requests.get(repo_url, headers=_get_headers(), timeout=10)
			repo_response.raise_for_status()
			from_branch = repo_response.json().get("default_branch", "main")
		except requests.exceptions.RequestException as exc:
			raise GitHubError(f"Failed to get repository info: {exc}") from exc

	# Get the SHA of the from_branch
	ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{from_branch}"
	try:
		ref_response = requests.get(ref_url, headers=_get_headers(), timeout=10)
		ref_response.raise_for_status()
		sha = ref_response.json().get("object", {}).get("sha")
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to get branch SHA: {exc}") from exc

	# Create the new branch
	create_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
	payload = {
		"ref": f"refs/heads/{branch_name}",
		"sha": sha,
	}

	try:
		response = requests.post(create_url, headers=_get_headers(), json=payload, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to create branch: {exc}") from exc

	data = response.json()
	result = {
		"branch_name": branch_name,
		"ref": data.get("ref"),
		"sha": data.get("object", {}).get("sha"),
		"url": data.get("url"),
	}

	await ctx.info(f"Created branch '{branch_name}' in {owner}/{repo}")
	return result



async def list_commits(
	ctx: Context[ServerSession, None],
	owner: str,
	repo: str,
	branch: str = "",
	max_results: int = 10,
) -> dict[str, Any]:
	"""List commits for a GitHub repository.

	Args:
		owner: Repository owner.
		repo: Repository name.
		branch: Branch name. Defaults to default branch.
		max_results: Maximum number of commits to return. Defaults to 10.

	Returns:
		Dictionary with list of commits.
	"""
	url = f"https://api.github.com/repos/{owner}/{repo}/commits"
	params = {
		"per_page": min(max_results, 100),
	}
	if branch:
		params["sha"] = branch

	try:
		response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
		response.raise_for_status()
	except requests.exceptions.RequestException as exc:
		raise GitHubError(f"Failed to list commits: {exc}") from exc

	data = response.json()
	commits = []
	for item in data:
		commits.append({
			"sha": item.get("sha"),
			"message": item.get("commit", {}).get("message"),
			"author": item.get("commit", {}).get("author", {}).get("name"),
			"date": item.get("commit", {}).get("author", {}).get("date"),
			"url": item.get("html_url"),
			"committer": item.get("commit", {}).get("committer", {}).get("name"),
		})

	await ctx.info(f"Retrieved {len(commits)} commits from {owner}/{repo}")
	return {
		"repository": f"{owner}/{repo}",
		"branch": branch if branch else "default",
		"count": len(commits),
		"commits": commits,
	}

