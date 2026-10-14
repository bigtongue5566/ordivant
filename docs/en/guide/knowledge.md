# Ordivant Knowledge

Knowledge stores traceable specifications, decisions, and background material. Each Space has an independent membership scope. Document contents use immutable versions, and search matches the titles and body text actually stored.

![Knowledge document with content, published versions, and citations](/screenshots/knowledge-en.png)

<span id="建立文件與版本"></span>
<span id="创建文档与版本"></span>

## Create a document and publish versions

1. An Identity administrator creates a Space and its resource scope with a unique key, name, and description. Afterward, grant Knowledge manager, writer, or reader access to members.
2. Select the Space and create a document with a title, summary, body, and tags. Initial creation stores the document and `v1` together.
3. Under “Sources and provenance,” add the Work, Code, or external sources used by the document. A source is a traceable reference; it does not grant its readers access to the source product.
4. To change an existing document, edit the **Shared draft** on its latest-version page. Wait for **Saved**, select **Publish new version**, enter a change summary, optional version title, and citations, then confirm. The system creates a new version; earlier versions, hashes, and citations remain unchanged. If another editor updated the draft, review the latest merged content before publishing again.

Readers can search titles, body text, and tags, then open a document and view an exact version. The page shows its version URI, creation time, content SHA-256, change summary, and sources. Search is persistent text search; this product does not provide vector indexing or RAG.

## Collaborate on a shared draft {#shared-draft-collaboration}

Knowledge Writers and Managers can edit the shared Markdown draft on a document's latest-version page. Readers can view the shared draft but cannot edit it. The Space's access scope also applies to Agents. This workflow does not need an LLM.

1. Open the document's latest version. In **Shared draft**, select **Edit** and write or revise the body. Switch to **Preview** to inspect formatting. The online-collaborator list shows signed-in members editing together. Agent updates through REST or MCP record the author in audit events.
2. Watch the draft status. **Connected** and **Saved** mean the server confirmed the changes; other connected editors receive the merged content. If the page says **Reconnecting** or shows **changes waiting to save**, keep it open. Unconfirmed offline changes remain only in the current browser tab's memory and may be lost if you close or reload it.
3. Other Writers and Managers can edit at the same time, and their changes merge into the same draft. Agents can read and update this draft through REST or MCP. Do not use another API to replace the entire body over other editors' changes.
4. To create a citable release, wait for a live connection and **Saved** status, select **Publish new version**, enter a change summary, and confirm. Only a live, saved draft can be published. Publication creates an immutable version and keeps earlier versions in the history.

If publication reports a version conflict, reload the shared draft, check the latest version and merged content, make any needed changes, and wait for **Saved** before publishing again. If access is revoked, the draft becomes read-only; ask an administrator to restore the Space grant before continuing.

<span id="引用特定版本"></span>

## Cite an exact version

The canonical URI for a document version is:

```text
ordivant://knowledge/spaces/{space_id}/documents/{document_id}/versions/{version}
```

Copy the complete URI from the version view and retain `/versions/{version}` in a citation. Do not link only to the mutable document home page. Record the URI in Work Task inputs or evidence, or add it as a Knowledge source when opening a Code pull request. A Knowledge version reference does not query or authorize data in another product; readers still need access to the Space.

<span id="記錄決策"></span>
<span id="记录决策"></span>

## Record decisions

Create a title and body in “Decision records,” optionally linking related documents and supporting sources. Decisions retain their author and citations, making them suitable for recording a chosen direction, trade-offs, and the effective version. When a decision changes, create a new record rather than erasing the previous context.

<span id="權限與範圍"></span>
<span id="权限与范围"></span>

## Permissions and scope

- **Manager:** manages Spaces and their access scopes, and can create documents, publish versions, and record decisions.
- **Writer:** creates documents, edits shared drafts, publishes new versions, and records decisions in authorized Spaces.
- **Reader:** reads shared drafts and history, searches, and copies citations; cannot edit or publish.

Identity administrators grant membership in explicit Space scopes. Signing in to Knowledge does not grant access to every Space, and a URI is not cross-product authorization. See the [administration guide](administration.md) for managing members.

## Page trees and templates {#page-tree-and-templates}

In the document library, choose **New document** and select a built-in PRD, meeting notes, Architecture Decision Record (ADR), or Standard Operating Procedure (SOP) from **Document template**, or write from scratch. During creation, you can choose a **Parent document** in the same Space; the list displays the hierarchy with indentation. Writers and Managers can choose **Document structure** in the reader to change the parent or archive the document. Trees cannot cross Spaces or contain cycles.

Archived documents are hidden from the default search list. Turn on **Show archived** to manage them again. Archiving does not delete a document or its versions. If it has children, move each child to another parent before archiving it. A Space Writer or Manager can also choose **Create space template** in the new-document flow, then enter a name, description, and Markdown body. A custom template belongs only to that Space.

## Comments, Markdown, and version comparisons {#comment-format-compare-restore}

Select text in the rendered document preview, then add a comment under **Document comments**. The comment keeps the quoted text and the published version it refers to. Readers can view comments; Writers and Managers can comment, reply one level deep, resolve a thread, or reopen it. Comments are displayed as plain text. When the document changes, an older-version quote is marked as stale and is not silently moved to the new version.

The latest shared draft has bold, italic, link, image-Markdown, and table tools, plus a live preview. These controls insert Markdown into the same shared draft. The image tool inserts a URL and alt text; it does not upload an image. Canonical content remains the live-collaborative Markdown draft. This is not a second synchronized document or a full WYSIWYG block editor.

Writers and Managers can choose **Compare versions** in the reader and select two published versions to inspect their diff. After selecting a historical version, **Restore version** creates a new immutable version using that content; it never rewrites the old version. A stale current version or unpublished collaborator changes in the shared draft causes a conflict and stops the restore. Resolve the shared-draft conflict before trying again.
