# Documentation publishing and discoverability runbook

This maintainer runbook is excluded from the documentation website. The site
uses `docs/` directly; edit the existing guides rather than creating parallel
SEO pages. The planned URL is `https://pooyanazad.github.io/kube-saver/`.
It is not evidence that the site is already published or indexed.

## Build, preview and review

From the repository root, in a separate virtual environment:

```bash
python3 -m venv .venv-docs
source .venv-docs/bin/activate
python -m pip install -r requirements-docs.txt
python -m mkdocs build --strict
python scripts/validate_docs_site.py site
python -m mkdocs serve
```

The development server mirrors the `/kube-saver/` project path. Check desktop
and narrow/mobile layouts, keyboard navigation, search, and code scrolling.
The Documentation workflow builds PR previews as downloadable artifacts; it
does not publish on a push, PR, or merge. Runtime CI remains separate.
Historical screenshot plans and reports are excluded from the built site;
they are not current executable examples or extra indexable pages.

MkDocs and Material (9.7.7) are pinned in `requirements-docs.txt`. Material 9.7 entered
maintenance in November 2025, with critical fixes/security updates promised
for at least 12 months. Review upstream maintenance status before November
2026 and future updates; this build uses standard Markdown and a small config
to keep a later theme migration practical. No analytics, external fonts,
special AI schema, or `llms.txt` is required here.

## Save the approved GitHub About settings

On the repository's Code page, sign in as an owner/administrator and click the
gear beside **About**. Set:

- Description: `Kubernetes cost estimates and resource right-sizing with a Python CLI, terminal dashboard, HTML reports, and local change plans.`
- Website: `https://github.com/pooyanazad/kube-saver/blob/main/docs/README.md`
- Topics: `kubernetes`, `k8s`, `finops`, `cost-optimization`,
  `resource-rightsizing`, `devops`, `sre`, `platform-engineering`, `tui`, `cli`,
  `python`. Enter/accept each topic chip, then **Save changes**.

Reload the Code page and verify the description, website link, and all 11
topics. Read `description`, `homepage`, and `topics` from the repository API
if available to independently verify persistence. Do not silently substitute
the future Pages URL for the approved Website value; ask before changing it.

## Publish only after explicit approval

1. Review the draft PR, CI results, and preview. Obtain separate approval to
   merge and to publish; neither action is performed by this runbook.
2. After the approved merge, open repository **Settings → Pages**. Under
   **Build and deployment → Source**, select **GitHub Actions**. Do not select
   a branch source, which could publish without this workflow's manual gate.
3. Under **Settings → Environments → github-pages**, restrict deployment to
   `main`. Add an appropriate required reviewer if available for your setup.
4. Open **Actions → Documentation → Run workflow**, select `main`, and enable
   `publish_docs` only for an approved publication. The default is false.
   The build validates first; only the deploy job has Pages/OIDC permissions.
5. Wait for deployment success. Open the actual returned deployment URL and
   verify anonymous HTTPS access to the home, installation, FAQ, safety,
   RBAC, GitOps, CLI, configuration, and troubleshooting pages. Check search,
   narrow layouts, sitemap URLs, and canonical URLs against the live host.
   Do not report success from the build alone.

This workflow publishes static documentation only. It does not call the
release workflow, create tags, push a `gh-pages` branch, deploy Kubernetes
resources, or publish package/container releases.

## robots.txt on a project site

`docs/robots.txt` is copied to `/kube-saver/robots.txt`, but this is not the
authoritative crawl policy. Google reads the host root
`https://pooyanazad.github.io/robots.txt`. Inspect that URL after publication:
an absent file alone does not block crawling; an existing Disallow rule can.

If the owner also manages the separate `pooyanazad.github.io` user-site
repository, review its existing root policy and add an appropriate Allow rule
and the kube-saver sitemap declaration there. `host-robots.example.txt` is a
starting point, not a file to overwrite an existing policy blindly. Creating
or deploying that separate site is outside this project's approved scope.
Do not claim a robots file committed to github.com controls GitHub crawling.

## Google Search Console after the site is live

No Search Console ownership or sitemap submission is established by building
this site. The GitHub repository itself is not the verified property.

1. Sign in to Google Search Console with the owner's chosen Google account.
2. Choose **Add property → URL prefix** and enter the exact live HTTPS prefix
   `https://pooyanazad.github.io/kube-saver/`, including its trailing slash.
   Do not choose a Domain property for `github.io`; the owner does not control
   that domain's DNS.
3. Choose **HTML file** verification. Download Google's actual verification
   file and add it unchanged at the top level of `docs/` in a focused branch.
   Its filename and content must come from Google, not a made-up token. The
   MkDocs build copies it unchanged. Review, merge, and publish only with
   approval; check the exact public verification URL, then click **Verify**.
   Keep the verification file deployed for continued ownership.
4. In **Sitemaps**, submit the live
   `https://pooyanazad.github.io/kube-saver/sitemap.xml`. Record the submitted
   date and reported status; submission is not proof of indexing.
5. In **URL inspection**, inspect home, `getting-started/`, `faq/`, `safety/`,
   `rbac/`, `gitops/`, `cli-reference/`, `configuration/`, and
   `troubleshooting/`. Run **Test live URL** where useful. Record HTTP/access
   failures, crawl permissions, selected canonical, last crawl, and indexing
   status. Request indexing only for appropriate important URLs.
6. Check **Page indexing** and sitemap errors. Fix actual 404s, accidental
   `noindex`, canonical mismatch, blocked resources, or server errors. A
   pending/discovered page is not proof of a technical failure. After data
   accrues, review Search Console queries, clicks, and impressions monthly.

Google authentication, verification-file retrieval and Search Console access
require the owner unless an authorized integration exposes them. Keep actual
observations separate from planned actions and don't claim success without
the corresponding console response.

## Search visibility baseline and repeat procedure

The dated records in `visibility-baseline.json` are observations from the
available search service, not Google/Bing SERP ranks or AI citations. Its
underlying engine and user location were not exposed. A missing result means
only **not observed in the returned set**, not globally unindexed.

Keep these exact queries unchanged for comparisons:

- `open source Kubernetes cost analyzer`
- `Kubernetes cost optimization CLI`
- `Kubernetes right-sizing tool`
- `offline Kubernetes cost report`
- `Kubernetes resource waste analyzer`

Before publication and monthly afterward, manually check Google and Bing
signed out, with the same language/location and search depth (for example the
first 20 organic results). Use the same literal queries in any available AI
search product, record its product/model/mode and whether web search was used,
and save the response's actual source URLs. Never infer citations from a brand
mention. This is a manual tracking plan, not a scheduled automation.

For each run, record ISO timestamp/timezone, engine/product, query, locale,
device/mode, inspected scope, appeared/mentioned/cited flags, exact target and
returned URLs, observed organic position if available, and an evidence link
or retained screenshot. Use null/not-tested when access is unavailable. Never
invent a rank or treat an AI answer as a stable trend. Add observations to the
JSON list; compare like-for-like records, not different tools or query wording.
After publication, add the live Pages URL alongside the GitHub repository as
a tracked target. Improved visibility is a hypothesis until observed.

## Official references

- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [MkDocs configuration and canonical URLs](https://www.mkdocs.org/user-guide/configuration/)
- [Material maintenance announcement](https://squidfunk.github.io/mkdocs-material/changelog/)
- [Google AI search guidance](https://developers.google.com/search/docs/appearance/ai-features)
- [Google robots.txt location](https://developers.google.com/crawling/docs/robots-txt/create-robots-txt)
- [Search Console ownership verification](https://support.google.com/webmasters/answer/9008080)

## Section 3 preparation evidence, 9 October 2026

Base main: `c1dbb2200c618d61a7e6a77708d568facbf02488`; all three prior audit
PRs are present. README and package discovery metadata were already accurate;
their contents, package version/dependencies, runtime, manifests, Dockerfile,
and release workflow remain unchanged in this documentation proposal.

- Local Python 3.12 suite: 387 tests passed. Ruff, mypy (40 files including the
  new site validator), actionlint, and whitespace checks passed.
- MkDocs 1.6.1 / Material 9.7.7 strict production build passed. Validator
  checked 17 canonical pages, unique titles/descriptions, 1,314 internal
  links/assets/anchors, XML/gzip sitemap, viewport metadata, local assets and
  populated search index. Broken canonical, broken link, mismatched sitemap,
  and accidental noindex fixtures were correctly rejected.
- Existing source-example checks passed: 20 Markdown files, 116 local
  links/assets/anchors, 19 YAML blocks, 2 Python blocks, 48 shell blocks,
  8 CLI help checks, report/doctor flags, and FAQ arithmetic.
- Visual desktop/mobile interaction tests remain **unverified**: the cloud
  browser blocked localhost, the standard browser download was unusable, and
  an isolated packaged Chromium renderer could not launch in this execution
  environment. No UI test pass is claimed. Preview locally using the commands
  above or download the PR's `documentation-preview` CI artifact and serve it
  under `/kube-saver/`. Check keyboard access, mobile drawer, code scrolling,
  and a live search before approving publication.
- Repository API still reports the old About description, null homepage,
  empty Topics, and Pages disabled. The GitHub plugin exposes no settings
  write action; browser passkey authentication did not complete. The exact
  manual steps above remain required unless settings access becomes available.
- Five query observations are recorded with the available search service;
  direct Google/Bing ranks and AI citations were not tested. No Search Console
  property, ownership verification, sitemap submission or live Pages indexing
  has been claimed. Publication and inspection await owner approval/access.
