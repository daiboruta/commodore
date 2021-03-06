import difflib
import hashlib

import click

from git import Repo, Actor
from git.exc import GitCommandError, BadName


class RefError(ValueError):
    pass


def _normalize_git_ssh(url):
    # pylint: disable=import-outside-toplevel
    from url_normalize.url_normalize import normalize_userinfo, normalize_host, \
        normalize_path, provide_url_scheme
    from url_normalize.tools import deconstruct_url, reconstruct_url

    if '@' in url and not url.startswith('ssh://'):
        # Assume git@host:repo format, reformat so url_normalize understands
        # the URL
        host, repo = url.split(':')
        url = f"{host}/{repo}"
    # Import heavy lifting from url_normalize, simplify for Git-SSH usecase
    url = provide_url_scheme(url, 'ssh')
    urlparts = deconstruct_url(url)
    urlparts = urlparts._replace(
        userinfo=normalize_userinfo(urlparts.userinfo),
        host=normalize_host(urlparts.host),
        path=normalize_path(urlparts.path, scheme='https'),
    )
    return reconstruct_url(urlparts)


def checkout_version(repo, ref):
    """
    Checkout the commit `ref` resolves to in `repo`. If `ref` does not resolve
    to a commit, try to resolve `remotes/origin/{ref}` to a commit, and
    checkout that commit.  Always checkout as detached HEAD as that massively
    simplifies the implementation.
    """
    rev = None
    try:
        rev = repo.commit(f"{ref}")
    except BadName:
        pass
    try:
        if not rev:
            rev = repo.commit(f"remotes/origin/{ref}")
        repo.head.reference = rev
        repo.head.reset(index=True, working_tree=True)
    except GitCommandError as e:
        raise RefError(f"Failed to checkout revision '{ref}'") from e
    except BadName as e:
        raise RefError(f"Revision '{ref}' not found in repository") from e


def clone_repository(repository_url, directory, cfg):
    try:
        repo = Repo.clone_from(_normalize_git_ssh(repository_url), directory)
    except Exception as e:
        raise click.ClickException(
            f"While cloning git repository: {e}") from e
    try:
        _ = repo.head.commit
    except ValueError as e:
        click.echo(f" > {e}, creating initial commit for {directory}")
        commit(repo, "Initial commit", cfg)
    return repo


def update_remote(repo: Repo, remote_url):
    origin = repo.remotes.origin
    if origin.url != remote_url:
        with origin.config_writer as cw:
            cw.set("url", remote_url)
        try:
            origin.pull(prune=True)
            return True
        except Exception as e:
            raise click.ClickException(
                f"While fetching git repository: {e}") from e
    return False


def init_repository(path):
    return Repo(path)


def create_repository(path):
    return Repo.init(path)


def _NULL_TREE(repo):
    """
    An empty Git tree is represented by the C string "tree 0". The hash of the
    empty tree is always SHA1("tree 0\\0").  This method computes the
    hexdigest of this sha1 and creates a tree object for the empty tree of the
    passed repo.
    """
    null_tree_sha = hashlib.sha1(b'tree 0\0').hexdigest()  # nosec
    return repo.tree(null_tree_sha)


def _colorize_diff(line):
    if line.startswith('--- ') or \
       line.startswith('+++ ') or \
       line.startswith('@@ '):
        return click.style(line, fg='yellow')
    if line.startswith('+'):
        return click.style(line, fg='green')
    if line.startswith('-'):
        return click.style(line, fg='red')
    return line


def _compute_similarity(change):
    before = change.b_blob.data_stream.read().decode('utf-8').split('\n')
    after = change.a_blob.data_stream.read().decode('utf-8').split('\n')
    r = difflib.SequenceMatcher(a=before, b=after).ratio()
    similarity_diff = []
    similarity_diff.append(click.style(f"--- {change.b_path}", fg='yellow'))
    similarity_diff.append(click.style(f"+++ {change.a_path}", fg='yellow'))
    similarity_diff.append(f"Renamed file, similarity index {r*100:.2f}%")
    return similarity_diff


def stage_all(repo):
    index = repo.index

    # Stage deletions
    dels = index.diff(None)
    if dels:
        to_remove = []
        for c in dels.iter_change_type('D'):
            to_remove.append(c.b_path)
        if len(to_remove) > 0:
            index.remove(items=to_remove)

    # Stage all remaining changes
    index.add('*')
    # Compute diff of all changes
    try:
        diff = index.diff(repo.head.commit)
    except ValueError:
        # Assume that we're in an empty repo if we get a ValueError from
        # index.diff(repo.head.commit). Diff against empty tree.
        diff = index.diff(_NULL_TREE(repo))

    changed = False
    difftext = []
    if diff:
        changed = True
        for ct in diff.change_type:
            for c in diff.iter_change_type(ct):
                # Because we're diffing the staged changes, the diff objects
                # are backwards, and "added" files are actually being deleted
                # and vice versa for "deleted" files.
                if ct == 'A':
                    difftext.append(click.style(f"Deleted file {c.b_path}", fg='red'))
                elif ct == 'D':
                    difftext.append(click.style(f"Added file {c.b_path}", fg='green'))
                elif ct == 'R':
                    difftext.append(
                        click.style(
                            f"Renamed file {c.b_path} => {c.a_path}",
                            fg='yellow'))
                else:
                    if c.renamed_file:
                        # Just compute similarity ratio for renamed files
                        # similar to git's diffing
                        difftext.append('\n'.join(_compute_similarity(c)).strip())
                        continue
                    # Other changes should produce a usable diff
                    # The diff objects are backwards, so use b_blob as before
                    # and a_blob as after.
                    before = c.b_blob.data_stream.read().decode('utf-8').split('\n')
                    after = c.a_blob.data_stream.read().decode('utf-8').split('\n')
                    diff_lines = difflib.unified_diff(before, after, lineterm='',
                                                      fromfile=c.b_path, tofile=c.a_path)
                    diff_lines = [_colorize_diff(line) for line in diff_lines]
                    difftext.append('\n'.join(diff_lines).strip())

    return '\n'.join(difftext), changed


def commit(repo, commit_message, cfg):
    if cfg.username and cfg.usermail:
        author = Actor(cfg.username, cfg.usermail)
    else:
        author = Actor.committer(repo.config_reader())

    if cfg.trace:
        click.echo(f' > Using "{author.name} <{author.email}>" as commit author')

    repo.index.commit(commit_message, author=author, committer=author)


def add_remote(repo, name, url):
    return repo.create_remote(name, _normalize_git_ssh(url))
