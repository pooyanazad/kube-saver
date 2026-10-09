# PyPI Trusted Publishing owner setup

This is a separate manual publication route for verified GitHub release assets.
It does not create Git tags, edit GitHub releases, build a new package, push Docker
images, or run on pushes, PRs, tag creation, or release-note edits.

Before enabling publication, configure the GitHub `pypi` environment to allow
only the `main` branch and require owner approval where supported. Then sign in
to PyPI and establish ownership of `kube-saver`. For an existing owned project,
add a GitHub Trusted Publisher in that project's Publishing settings; for a new
project, create a pending publisher through account Publishing settings. A 404
response does not guarantee name availability.

Use these exact publisher values:

| Field | Value |
|---|---|
| Project name, if pending | `kube-saver` |
| GitHub owner | `pooyanazad` |
| Repository | `kube-saver` |
| Workflow filename | `pypi.yml` |
| Environment | `pypi` |

The owner must complete authentication, account security, ownership, and any
publisher authorization. No long-lived PyPI token belongs in GitHub or chat.

Run **Publish verified package to PyPI** on main first with `publish_pypi=false`.
For the reviewed v2.0.0 assets, the defaults pin tag `v2.0.0`, source commit
`aabcf088c0f1500728380beb9c060b59908d83e5`, and SHA256SUMS.txt digest
`dfaefb920456d7cf87c6a37d40ccf8bc19522c7b11fdb5d4a585cc3ea3a98206`.
The workflow requires successful latest main CI for the selected source and
verifies the remote tag, checksum manifest, distribution hashes,
source/metadata versions, Twine 7 checks (required for metadata 2.5), and the
actual installed CLI. It uses the
existing release assets instead of rebuilding them from a later main commit.

After all checks and publisher ownership requirements pass, dispatch again with
`publish_pypi=true` and approve the protected environment job. Only that job has
OIDC `id-token: write`. It rechecks the tag and hashes and refuses an existing
PyPI version; it never skips mismatched files. Network/authentication errors
stop publication. PyPI distribution files cannot be replaced after upload.

After publication, verify the project/version page, downloaded hashes, and a
fresh isolated PyPI installation. Only then update installation documentation
to promise `pip install kube-saver`. Keep historical releases and images intact.
