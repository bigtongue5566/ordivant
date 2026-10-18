# Third-party software

Ordivant's original source and documentation are licensed under MIT. This does not replace the licenses of dependencies or separately deployed services. Lockfiles record exact package versions; dependency distributions retain their own copyright and license files.

## JavaScript packages

The following direct dependencies were checked against installed package metadata for this release:

| Component | License | Source |
| --- | --- | --- |
| React / React DOM | MIT | https://github.com/facebook/react |
| Ant Design / icons | MIT | https://github.com/ant-design/ant-design |
| CodeMirror state / view / Markdown language | MIT | Respective `@codemirror` package metadata and upstream repositories |
| Yjs / y-protocols / y-codemirror.next | MIT | https://github.com/yjs |
| Pi Durable / Pi AI / Chord 1.0.3 | MIT | https://github.com/earendil-works/pi |
| MCP TypeScript client 2.3.1 | Apache-2.0 | https://github.com/modelcontextprotocol/typescript-sdk |
| TypeScript / Vite / VitePress | Apache-2.0 / MIT / MIT | Respective package metadata and upstream repositories |

The frontend and documentation build tools carry applicable dependency notices in their installed distributions and generated assets. `node_modules` and generated sites are not committed as source.

## Python and container dependencies

Python service dependencies are installed from the committed `uv.lock` files. FastAPI, SQLAlchemy, cryptography, psycopg, the MCP SDK and their transitive dependencies retain their upstream licenses. In particular, using MIT for Ordivant does not relicense LGPL components such as psycopg or libraries shipped in container base images.

Knowledge uses pycrdt 0.12.50 (MIT, copyright David Brochart) to merge Yjs updates. Its installed distribution includes the license at `pycrdt-0.12.50.dist-info/licenses/LICENSE`; upstream source is https://github.com/y-crdt/pycrdt.

PostgreSQL, Node.js, Python, optional Gitea and optional Keycloak are separately distributed services/runtime images referenced by Compose or Dockerfiles. Their images contain additional operating-system packages with their own notices. Git in the sandbox retains its GPL license. Anyone redistributing modified images must review and satisfy the applicable upstream redistribution obligations; the Ordivant repository is not a replacement for those notices.

## Scope

This is an orientation to the dependency boundaries, not an exhaustive legal inventory or a declaration that all transitive software uses MIT. No third-party trademarks or affiliations are granted by the Ordivant license. No proprietary model weights, provider credentials, account data or customer documents are included.
